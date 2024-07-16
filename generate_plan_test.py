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

    # retrieve user details from chat or db
    user_data = _extract_user_data(user_id=user_id, chat_id=chat_id)
    # update the last week summary if exists
    update_weekly_summary(user_id=user_id)

    # retrieve all previous weeks of user fitness plans
    old_weekly_training_plans = _get_all_old_weekly_training_plans(user_id=user_id)
    week_number = 1 if len(old_weekly_training_plans) == 0 else len(old_weekly_training_plans)+1

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
    # save the new weekly training plan in weekly-training-plans collection
    week_id = _save_new_weekly_training_plan(
        fitness_plan=json.loads(response), 
        start_of_week=start_of_week
    )
    # update the user overall training plan with the new week training plan in training-plans collection.
    _update_overall_training_plan(
        user_id=user_id, 
        week_id=week_id, 
        week_number=week_number, 
        start_of_week=start_of_week)
    # print(json.loads(response))
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

def update_weekly_summary(user_id: str):
    """
    update weekly summary of the last week.
    """
    training_plan_dboperations = DbOperations("training-plans")
    try: 
        plan_query = {"user_id": user_id}
        training_plans = training_plan_dboperations.read_one_from_mongodb(plan_query)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving from training-plans collection: {str(e)}"
        )

    year = str(datetime.now().year)
    
    # if exist, get the latest week and update that week training plan summary
    if training_plans:
        week_keys = []
        del training_plans["_id"]
        week_keys = training_plans["training_plan"][year].keys()

        if not week_keys:
            last_week = sorted(week_keys)[-1]
            week_id = training_plans["training_plan"][year][last_week]["week_id"]

            weekly_plan_dboperations = DbOperations("weekly-training-plans")
            try: 
                week_query = {"week_id": week_id}
                last_week_plan = weekly_plan_dboperations.read_one_from_mongodb(week_query)
            except Exception as e:
                error_message = (
                    f"Error retrieving the last week from weekly-training-plans collection "
                    f"for week_id: {week_id} and user_id: {user_id} with the error: {str(e)}"
                )
                print(error_message)
                raise HTTPException(status_code=500, detail=error_message)
            if last_week_plan["_id"]:
                del last_week_plan["_id"]

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            with open("prompts/weekly_plan_summary.txt", "r") as file:
                system_message = file.read()
                system_message = system_message.replace("last_week_plan", json.dumps(last_week_plan)) 
            user_message = "Create the summary of the last week training plan."

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
            )
            response = response.choices[0].message.content
            # print(response)
            new_value = {"$set": {f"training_plan.{year}.{last_week}.summary": response}}
            try:
                training_plan_dboperations.update_from_mongodb(plan_query, new_value)
            except Exception as e:
                error_message = (
                    f"Error updating training plan with the new weekly training plan "
                    f"for week_id: {week_id} in MongoDB: {e}"
                )
                print(error_message)
                raise HTTPException(status_code=500, detail=error_message)

def _extract_user_data(
    user_id: str, 
    chat_id: str | None = None) -> list[dict[str, str]]:
    """
    Retrieve user data from chat if chat_id is provided else from user-details collection.
    """
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
                raise HTTPException(status_code=404, detail="User data not found for user_id: " + user_id)
            print("Successfully retrieved user data.")
        except HTTPException as he:
            raise he
        except Exception as e:
            error_message = f"Error reading user data for user_id: {user_id} from MongoDB: {e}"
            print(error_message)
            return {"status": "error", "message": error_message}, 500

        for data in user_data:
            data.pop("_id", None)
    
    return user_data

def _get_all_old_weekly_training_plans(user_id: str) -> list[dict[str, str]]:
    """
    Retrieve and return the fitness plans of all the past weeks.
    """
    training_plan_dboperations = DbOperations("training-plans")
    training_plans = None
    try:
        plan_query = {"user_id": user_id}
        training_plans = training_plan_dboperations.read_one_from_mongodb(plan_query)
        print("Successfully retrieved user's old training plans.")
    except Exception as e:
        error_message = f"Error reading from training-plan collection for user: {user_id} with the error: {e}"
        print(error_message)
        return {"status": "error", "message": error_message}, 500

    # get all the week_ids and retrieve all the fitness plans based on week_ids
    year = str(datetime.now().year)
    if training_plans["_id"]:
        del training_plans["_id"]
    week_keys = training_plans["training_plan"][year].keys()
    week_ids = []
    for week_key in week_keys:
        week_ids.append(training_plans["training_plan"][year][week_key]["week_id"])
    # print(training_plans)

    old_weekly_training_plans = []
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    for week_id in week_ids:
        week_query = {"week_id": week_id}
        try:
            week_plan = weekly_plan_dboperations.read_one_from_mongodb(week_query)
            if week_plan["_id"]:
                del week_plan["_id"]
            old_weekly_training_plans.append(week_plan)
        except Exception as e:
            error_message = (
                f"Error retrieving from weekly-training-plans collection "
                f"for week_id: {week_id} with the error: {str(e)}"
            )
            print(error_message)
            raise HTTPException(status_code=500, detail=error_message)
    return old_weekly_training_plans

def _save_new_weekly_training_plan(fitness_plan: dict, start_of_week: str) -> str: 
    """
    Save the newly generated weekly training plan in weekly-training-plans collection and return week_id
    """
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    week_id = f"{uuid.uuid4()}"
    fitness_plan["week_id"] = week_id
    fitness_plan["start_date"] = start_of_week
    try:
        weekly_plan_dboperations.write_to_mongodb(fitness_plan)
    except Exception as e:
        error_message = (
            f"Error saving in weekly-training-plans collection "
            f"for week_id: {week_id} with the error: {e}"
        )
        print(error_message)
        return {"status": "error", "message": error_message}, 500
    print("Weekly training plan is successfully saved in weekly training plan db.")
    return week_id

def _update_overall_training_plan(
    user_id: str, 
    week_id: str, 
    week_number: int, 
    start_of_week: str) -> None:
    """
    Update the user overall traning plan from training-plans collection with 
    week_id, start_date and summary of the week.
    """
    training_plan_dboperations = DbOperations("training-plans")
    entry = {"week_id": week_id, "start_date": start_of_week, "summary": ""}
    year = str(datetime.now().year)
    week = f"week {week_number}"
    query = {"user_id": user_id}
    new_value = {"$set": {f"training_plan.{year}.{week}": entry}}
    try:
        training_plan_dboperations.update_from_mongodb(query, new_value)
    except Exception as e:
        error_message = (
            f"Error updating training plan for user: {user_id} "
            f"with the new weekly training plan in MongoDB: {e}"
        )
        print(error_message)
        return {"status": "error", "message": error_message}, 500
    print("Weekly training plan is successfully updated from user training plans.")

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
