from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db_operations import DbOperations
from authorization import admin_required, user_or_admin_required
from openai import OpenAI
from datetime import datetime, timedelta
import os
import json
from typing import List
import uuid
from services.onboarding_assistant import OnboardingAssistant

# Load .env file
load_dotenv()

router = APIRouter()


class UpdateStatusRequest(BaseModel):
    date: str
    status: List[str]


@router.get("/generateWeeklyPlan")
async def generateWeeklyPlan(
    user_id: str, 
    chat_id: str | None = None,
    _: dict = Depends(user_or_admin_required)
):

    # retrieve user details from db
    user_details_dboperations = DbOperations("user-details")
    if chat_id:
        # Onboard first-time user. Summarize assessment conversation.
        chat_history = _get_chat_history(chat_id)
        client = OpenAI()
        assistant = OnboardingAssistant(client)
        user_data = assistant.summarize(chat_history)
    else:
        try:
            user_data = user_details_dboperations.read_from_mongodb(query_param=user_id)
            if not user_data:
                raise HTTPException(status_code=404, detail="User data not found")
            print("Successfully retrieved user data.")
        except Exception as e:
            print(f"Error reading user data from MongoDB: {e}")
            return {"status": "error", "message": str(e)}, 500

        for data in user_data:
            data.pop("_id", None)

    # retrieve all previous weeks of user fitness plans in sorted order
    training_plan_dboperations = DbOperations("training-plans")
    training_plans = None
    try:
        plan_query = {"user_id": user_id}
        training_plans = training_plan_dboperations.read_one_from_mongodb(plan_query)
        print("Successfully retrieved user's old training plans.")
    except Exception as e:
        print(f"Error reading previous training plan from MongoDB: {e}")
        return {"status": "error", "message": str(e)}, 500

    week_ids = []
    week_keys = []
    year = str(datetime.now().year)
    # if exist, generate a new plan with the information from previous weeks fitness plans
    if training_plans:
        del training_plans["_id"]
        week_keys = training_plans["training_plan"][year].keys()
    else:
        week = 1
    for week_key in week_keys:
        week_ids.append(training_plans["training_plan"][year][week_key]["week_id"])
    print(training_plans)

    old_weekly_training_plans = []
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    if week_ids:
        for week_id in week_ids:
            week_query = {"week_id": week_id}
            try:
                week_plan = weekly_plan_dboperations.read_one_from_mongodb(week_query)
                if week_plan["_id"]:
                    del week_plan["_id"]
                old_weekly_training_plans.append(week_plan)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error retrieving weekly training plan using week id: {str(e)}",
                )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    start_of_week = (
        datetime.now() - timedelta(days=datetime.now().weekday())
    ).strftime("%Y-%m-%d")
    current_day = datetime.now().strftime("%Y-%m-%d")
    with open("prompts/generate_fitness_plan_system_message.txt", "r") as file:
        system_message = file.read()
        system_message = system_message.replace("{user_data}", json.dumps(user_data))
        system_message = system_message.replace(
            "{start_of_week}", json.dumps(start_of_week)
        )
        system_message = system_message.replace(
            "{current_day}", json.dumps(current_day)
        )
        system_message = system_message.replace(
            "{old_training_plans}", json.dumps(old_weekly_training_plans)
        )
    # with open("prompts/generate_fitness_plan_user_message.txt", "r") as file:
    #     user_message = file.read()
    user_message = "Create a workout plan based on the given information."

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
    )
    response = response.choices[0].message.content
    print("Plan is successfully generated.")

    # load the new training plan to store in training plan db and weekly training plan db
    fitness_plan = json.loads(response)
    week_id = f"{uuid.uuid4()}"
    fitness_plan["week_id"] = week_id
    # start_of_week = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
    fitness_plan["start_date"] = start_of_week
    try:
        weekly_plan_dboperations.write_to_mongodb(fitness_plan)
    except Exception as e:
        print(f"Error saving weekly training plan in MongoDB: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error saving weekly training plan: {str(e)}"
        )
    print("Weekly training plan is successfully saved in weekly training plan db.")

    # add the user overall training plan with the new week training plan.
    entry = {"week_id": week_id, "start_date": start_of_week, "summary": ""}
    week = f"week {len(week_keys)+1}"
    query = {"user_id": user_id}
    new_value = {"$set": {f"training_plan.{year}.{week}": entry}}
    try:
        training_plan_dboperations.update_from_mongodb(query, new_value)
    except Exception as e:
        print(
            f"Error updating training plan with the new weekly training plan in MongoDB: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error updating training plan with the new weekly training plan in MongoDB: {str(e)}",
        )
    print("Weekly training plan is successfully updated from user training plans.")

    return json.loads(response)


@router.get("/getWeeklyTrainingPlan")
async def get_weekly_training_plan(user_id: str, date: str):
    # Convert the input date string to a datetime object
    target_date = datetime.strptime(date, "%Y-%m-%d")

    # Retrieve the training plan for the user
    training_plan_dboperations = DbOperations("training-plans")
    try:
        plan_query = {"user_id": user_id}
        training_plan = training_plan_dboperations.read_one_from_mongodb(plan_query)
        if not training_plan:
            raise HTTPException(
                status_code=404, detail="Training plan not found for the user"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving training plan: {str(e)}"
        )

    # Find the correct week for the given date
    year = str(target_date.year)
    if year not in training_plan["training_plan"]:
        raise HTTPException(
            status_code=404, detail="No training plan found for the specified year"
        )

    week_id = None
    for _, week_data in training_plan["training_plan"][year].items():
        week_start = datetime.strptime(week_data["start_date"], "%Y-%m-%d")
        week_end = week_start + timedelta(days=6)
        if week_start <= target_date <= week_end:
            week_id = week_data["week_id"]
            break
    if not week_id:
        raise HTTPException(
            status_code=404, detail="No matching week found for the given date"
        )

    # Retrieve the weekly training plan
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    try:
        weekly_plan_query = {"week_id": week_id}
        weekly_plan = weekly_plan_dboperations.read_one_from_mongodb(weekly_plan_query)
        if not weekly_plan:
            raise HTTPException(
                status_code=404, detail="Weekly training plan not found"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving weekly training plan: {str(e)}"
        )

    # Remove the _id field from the response
    weekly_plan.pop("_id", None)

    return weekly_plan


@router.put("/updateExerciseStatus/{week_id}")
async def updateExerciseStatus(week_id: str, request: UpdateStatusRequest):

    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    week_query = {"week_id": week_id}
    week_plan = None
    try:
        week_plan = weekly_plan_dboperations.read_one_from_mongodb(week_query)
        if not week_plan:
            raise HTTPException(
                status_code=404, detail="Weekly training plan not found"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving weekly training plan: {str(e)}"
        )

    update_operations = {}
    for workout in week_plan["workouts"]:
        if workout["date"] == request.date:
            for idx in range(len(workout["exercises"])):
                update_operations[f"workouts.$.exercises.{idx}.status"] = (
                    request.status[idx]
                )

    if update_operations:
        update_query = {"$set": update_operations}
        match_query = {"week_id": week_id, "workouts.date": request.date}
        try:
            weekly_plan_dboperations.update_from_mongodb(match_query, update_query)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error updating status of weekly training plan: {str(e)}",
            )

    print("Successfully updated all the statuses for: " + request.date)
    return {
        "status": "success",
        "message": "Exercise statuses updated successfully",
    }, 200


def _get_chat_history(chat_id: str) -> list[dict[str, str]]:
    """
    Retrieve chat history from the database.
    """
    db_operations = DbOperations("chat-history")
    chat_document = db_operations.collection.find_one({"chat_id": chat_id})
    if chat_document and "messages" in chat_document:
        return [
            {"role": m["role"], "content": m["content"]}
            for m in chat_document["messages"]
        ]
    return []
