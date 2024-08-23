from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db.db_operations import DbOperations
from authorization import admin_required, user_or_admin_required
from openai import OpenAI
from datetime import datetime, timedelta
from typing import List
import os
import json
import uuid
import logging
import traceback
from routers.user_profile import get_user_id_internal
from services.onboarding_assistant import OnboardingAssistant
from services.workout_journal_assistant import WorkoutJournalAssistant
from .helpers import generate_plan_helpers as gph

# Load .env file
load_dotenv()

router = APIRouter()
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class UpdateStatusRequest(BaseModel):
    date: str
    status: List[str]


@router.get("/generateWeeklyPlan")
async def generateWeeklyPlan(
    chat_id: str | None = None, current_user: dict = Depends(user_or_admin_required)
):
    """
    Generate weekly training plan for given user.
    """
    user_id = await get_user_id_internal(current_user["email"])
    start_of_week = (
        datetime.now() - timedelta(days=datetime.now().weekday())
    ).strftime("%Y-%m-%d")
    year = str(datetime.now().year)

    # TODO: FOR TESTING PURPOSE, TO BE UNCOMMENTED
    # validate if weekly training plan is not already generated for the same week
    # if not gph._validate_generate_weekly_plan(user_id, start_of_week, year):
    #     error_message = f"The plan is already generated for the week: {start_of_week}"
    #     logger.error(error_message)
    #     logger.error(traceback.format_exc())
    #     return {
    #         "status": "error",
    #         "message": error_message,
    #     }, 400

    # retrieve user details from chat or db
    user_data = gph._extract_user_data(user_id=user_id, chat_id=chat_id)
    # update the last week summary if exists
    gph.update_weekly_summary(user_id=user_id)

    # retrieve all previous weeks of user fitness plans
    old_weekly_training_plans = gph._get_all_old_weekly_training_plans(
        user_id=user_id, year=year
    )
    week_number = (
        1 if len(old_weekly_training_plans) == 0 else len(old_weekly_training_plans) + 1
    )

    # TODO: FOR TESTING PURPOSE, TO BE REMOVED
    temp_start_of_week = gph._get_last_week_start_date(user_id)
    if temp_start_of_week is not None:
        start_of_week = (datetime.strptime(temp_start_of_week, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
    logger.info("Plan is successfully generated.")
    # save the new weekly training plan in weekly-training-plans collection
    week_id = gph._save_new_weekly_training_plan(
        user_id=user_id, fitness_plan=json.loads(response), start_of_week=start_of_week
    )
    # update the user overall training plan with the new week training plan in training-plans collection.
    gph._update_overall_training_plan(
        user_id=user_id,
        week_id=week_id,
        week_number=week_number,
        start_of_week=start_of_week,
        year=year,
    )
    logger.info("Plan is successfully stored in db.")
    return json.loads(response)


@router.get("/getWeeklyTrainingPlan")
async def get_weekly_training_plan_api(
    date: str, current_user: dict = Depends(user_or_admin_required)
):
    """
    API endpoint to get weekly training plan of given user.
    """
    target_date = datetime.strptime(date, "%Y-%m-%d")
    user_id = await get_user_id_internal(current_user["email"])
    return await gph._get_weekly_training_plan_internal(target_date, user_id)


@router.put("/updateExerciseStatus/{week_id}")
async def updateExerciseStatus(week_id: str, request: UpdateStatusRequest):
    """
    Update exercise statuses of given date based on week_id.
    """
    weekly_plan = gph._get_weekly_training_plan(week_id)
    # update all exercise statuses of requested date
    update_operations = {}
    for workout in weekly_plan["workouts"]:
        if workout["date"] == request.date:
            for idx in range(len(workout["exercises"])):
                update_operations[f"workouts.$.exercises.{idx}.status"] = (
                    request.status[idx]
                )
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    if update_operations:
        update_query = {"$set": update_operations}
        match_query = {"week_id": week_id, "workouts.date": request.date}
        try:
            weekly_plan_dboperations.update_from_mongodb(match_query, update_query)
        except Exception as e:
            error_message = f"Error updating status of week_id: {week_id} with date: {request.date} with error: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)

    logger.info("Successfully updated all the statuses for: " + request.date)

    # update workout summary of given date.
    daily_plan = gph._get_daily_training_plan(week_id, request.date)
    client = OpenAI()
    with open("prompts/daily_plan_summary.txt", "r") as file:
        system_message = file.read()
        system_message = system_message.replace("daily_plan", json.dumps(daily_plan))
    user_message = "Create the short summary of the given day training plan."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
    )
    response = response.choices[0].message.content
    daily_plan_summary = {f"workouts.$.summary": (response)}

    update_query = {"$set": daily_plan_summary}
    match_query = {"week_id": week_id, "workouts.date": request.date}
    try:
        weekly_plan_dboperations.update_from_mongodb(match_query, update_query)
    except Exception as e:
        error_message = f"Error updating daily summary of week_id: {week_id} for date: {request.date} with error: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)

    return {
        "status": "success",
        "message": "Exercise statuses and summary are updated successfully",
    }, 200


@router.get("/updateDailySummary")
async def update_daily_summary(
    date: str, chat_id: str, current_user: dict = Depends(user_or_admin_required)
):
    """
    Complete the daily workout summary.
    Based on weekly_training_plan and chat_history between user and assistant.
    Summarize the workout and update the "summary" field in the weekly_training_plan document of the given date.
    """
    chat_history = gph._get_chat_history(chat_id)
    client = OpenAI()
    assistant = WorkoutJournalAssistant(client)
    checkin_summary = await assistant.summarize(
        date, current_user["email"], chat_history
    )

    # Update the summary in the database
    user_id = await get_user_id_internal(current_user["email"])
    target_date = datetime.strptime(date, "%Y-%m-%d")
    weekly_plan = await gph._get_weekly_training_plan_internal(target_date, user_id)

    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    update_query = {"$set": {"workouts.$.summary": checkin_summary}}
    match_query = {"week_id": weekly_plan["week_id"], "workouts.date": date}

    try:
        weekly_plan_dboperations.update_from_mongodb(match_query, update_query)
    except Exception as e:
        error_message = f"Error updating summary for date: {date} with error: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)

    return {"status": "success", "message": "Daily summary updated successfully"}, 200


# TODO: for testing to update multiple daily summary based on week_id
@router.put("/updateAllDailySummaries/{week_id}")
async def update_all_daily_summaries(
    week_id: str, current_user: dict = Depends(user_or_admin_required)
):
    user_id = await get_user_id_internal(current_user["email"])
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    weekly_plan = weekly_plan_dboperations.read_one_from_mongodb({"week_id": week_id, "user_id": user_id})
    
    if not weekly_plan:
        raise HTTPException(status_code=404, detail="Weekly plan not found")

    client = OpenAI()
    assistant = WorkoutJournalAssistant(client)

    for workout in weekly_plan["workouts"]:
        date = workout["date"]
        summary = await assistant.summarize(date, current_user["email"], [])

        update_query = {"$set": {"workouts.$.summary": summary}}
        match_query = {"week_id": week_id, "user_id": user_id, "workouts.date": date}

        try:
            weekly_plan_dboperations.update_from_mongodb(match_query, update_query)
        except Exception as e:
            logger.error(f"Error updating summary for date: {date} with error: {str(e)}")
            logger.error(traceback.format_exc())
            continue

    return {"status": "success", "message": "All daily summaries updated successfully"}, 200
