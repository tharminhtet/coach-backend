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


class GenerateWeeklyPlanRequest(BaseModel):
    comment: str | None = None
    chat_id: str | None = None


@router.post("/generateWeeklyPlan")
async def generateWeeklyPlan(
    request: GenerateWeeklyPlanRequest,
    current_user: dict = Depends(user_or_admin_required),
):
    """
    Generate weekly training plan for given user.
    """
    user_id = await get_user_id_internal(current_user["email"])
    start_of_week = (
        datetime.now() - timedelta(days=datetime.now().weekday())
    ).strftime("%Y-%m-%d")
    year = str(datetime.now().year)
    # validate if weekly training plan is not already generated for the same week
    if not gph._validate_generate_weekly_plan(user_id, start_of_week, year):
        error_message = f"The plan is already generated for the week: {start_of_week}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": error_message,
        }, 400

    # retrieve user details from chat or db
    user_data = gph._extract_user_data(user_id=user_id, chat_id=request.chat_id)
    user_memories = gph._extract_user_memories(user_id=user_id)
    # update the last week summary if exists
    gph.update_weekly_summary(user_id=user_id)

    # retrieve all previous weeks of user fitness plans
    old_weekly_training_plans = gph._get_all_old_weekly_training_plans(
        user_id=user_id, year=year
    )
    week_number = (
        1 if len(old_weekly_training_plans) == 0 else len(old_weekly_training_plans) + 1
    )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    current_day = datetime.now().strftime("%Y-%m-%d")
    with open("prompts/generate_fitness_plan_system_message.txt", "r") as file:
        system_message = file.read()
    with open("prompts/generate_fitness_plan_user_message.txt", "r") as file:
        user_message = file.read()
        user_message = user_message.replace(
            "{instructions}", json.dumps(user_memories, indent=2)
        )
        user_message = user_message.replace(
            "{user_data}", json.dumps(user_data, indent=2)
        )
        user_message = user_message.replace(
            "{start_of_week}", json.dumps(start_of_week)
        )
        user_message = user_message.replace("{current_day}", current_day)
        user_message = user_message.replace(
            "{old_training_plans}", json.dumps(old_weekly_training_plans, indent=2)
        )
        user_message = user_message.replace("{comment}", request.comment)

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


@router.get("/generateQuickWorkout")
async def generate_quick_workout_plan(
    date: str, current_user: dict = Depends(user_or_admin_required)
):
    """
    Create a new quick workout plan for 45 minutes based on previous week workouts
    and the current week workout.
    """

    # retrieve the workout plan for the current week
    current_week_workout = await get_weekly_training_plan_api(date, current_user)
    if not current_week_workout:
        error_message = "Quick workout session cannot be generated before the weekly workout plan is generated."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=error_message)

    # Check if a workout already exists for the given date
    existing_workout = next(
        (
            workout
            for workout in current_week_workout["workouts"]
            if workout["date"] == date
        ),
        None,
    )
    if existing_workout:
        error_message = f"A workout already exists for the date: {date}"
        logger.error(error_message)
        raise HTTPException(status_code=400, detail=error_message)

    user_id = await get_user_id_internal(current_user["email"])
    # retrieve user details from db
    user_data = gph._extract_user_data(user_id=user_id, chat_id=None)

    # retrieve all previous weeks of user fitness plans
    current_date = datetime.strptime(date, "%Y-%m-%d").date()

    old_weekly_training_plans = gph._get_all_old_weekly_training_plans(
        user_id=user_id, year=str(current_date.year)
    )

    client = OpenAI()
    with open("prompts/generate_quick_workout_plan_system_message.txt", "r") as file:
        system_message = file.read()
        system_message = system_message.replace("{user_data}", json.dumps(user_data))
        system_message = system_message.replace(
            "{current_week_workout}", json.dumps(current_week_workout)
        )
        system_message = system_message.replace(
            "{current_date}", current_date.isoformat()
        )
        system_message = system_message.replace(
            "{old_training_plans}", json.dumps(old_weekly_training_plans)
        )
    user_message = (
        "Create a workout plan for a current date based on the given information."
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
    )
    quick_workout = json.loads(response.choices[0].message.content)
    logger.info("Quick workout plan is successfully generated.")

    # Update the current week's workout plan with the new quick workout
    week_id = current_week_workout["week_id"]
    weekly_plan_dboperations = DbOperations("weekly-training-plans")

    try:
        update_query = {"$push": {"workouts": quick_workout}}
        weekly_plan_dboperations.update_from_mongodb({"week_id": week_id}, update_query)

        logger.info(
            f"Quick workout for date {date} successfully added to the weekly plan."
        )
        return quick_workout

    except Exception as e:
        error_message = (
            f"Error updating weekly training plan with quick workout: {str(e)}"
        )
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)


class LogWorkoutRequest(BaseModel):
    date: str
    chat_id: str
    should_replace: bool


@router.post("/logWorkout")
async def log_workout(
    request: LogWorkoutRequest,
    current_user: dict = Depends(user_or_admin_required),
):
    """
    Add or update a workout based on chat_id for a given date.
    """
    # retrieve the workout plan for the current week
    current_week_workout = await get_weekly_training_plan_api(
        request.date, current_user
    )
    if not current_week_workout:
        error_message = (
            "Logging workout cannot be done before generating a weekly workout."
        )
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=error_message)

    current_date = datetime.strptime(request.date, "%Y-%m-%d").date().isoformat()
    chat_history, _, _ = gph._get_chat_history(request.chat_id, True)
    formatted_chat_history = gph.format_chat_history(chat_history)

    client = OpenAI()
    with open("prompts/log_workout_system_message.txt", "r") as file:
        system_message = file.read()
    with open("prompts/log_workout_user_message.txt", "r") as file:
        user_message = file.read()
        user_message = user_message.replace("{workout_date}", current_date)
        user_message = user_message.replace("{chat_history}", formatted_chat_history)

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
    )

    workout_log = json.loads(response.choices[0].message.content)
    logger.info("Quick workout log is successfully generated.")

    week_id = current_week_workout["week_id"]
    try:
        gph._update_or_insert_workout_for_specific_date(
            week_id, current_date, workout_log, request.should_replace
        )
        logger.info(
            f"Workout log for date: {request.date} successfully added/updated in the weekly plan."
        )
        return workout_log
    except Exception as e:
        error_message = (
            f"Error updating weekly training plan with workout log: {str(e)}"
        )
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)


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
    chat_history, _, _ = gph._get_chat_history(chat_id, True)
    client = OpenAI()
    assistant = WorkoutJournalAssistant(client)
    checkin_summary = await assistant.summarize(
        date, current_user["email"], chat_history
    )

    # Update the summary in the database
    user_id = await get_user_id_internal(current_user["email"])
    target_date = datetime.strptime(date, "%Y-%m-%d")
    weekly_plan = await gph._get_weekly_training_plan_internal(target_date, user_id)
    if weekly_plan:
        weekly_plan_dboperations = DbOperations("weekly-training-plans")
        update_query = {"$set": {"workouts.$.summary": checkin_summary}}
        match_query = {"week_id": weekly_plan["week_id"], "workouts.date": date}

        try:
            weekly_plan_dboperations.update_from_mongodb(match_query, update_query)
        except Exception as e:
            error_message = (
                f"Error updating summary for date: {date} with error: {str(e)}"
            )
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)

        return {"status": "success", "message": "Daily summary updated successfully"}


@router.put("/updateWorkoutByDate")
async def update_workout(
    week_id: str,
    date: str,
    chat_id: str,
    current_user: dict = Depends(user_or_admin_required),
):
    """
    Update the workout for a given date in the weekly-training-plans collection.
    """
    try:
        # Get user details
        user_id = await get_user_id_internal(current_user["email"])
        user_details = gph._extract_user_data(user_id=user_id)

        # Get chat history and format chat history
        chat_history, _, _ = gph._get_chat_history(chat_id, True)
        formatted_chat_history = ""
        for message in chat_history:
            formatted_chat_history += f"{message['role']} : {message['content']}\n"

        # Get original workout
        original_workout = gph.get_workout_by_date(week_id, date)

        # Generate new workout plan
        client = OpenAI()
        with open(
            "prompts/regenerate_specific_date_workout_system_message.txt", "r"
        ) as file:
            system_message = file.read()
            system_message = system_message.replace(
                "{user_details}", json.dumps(user_details)
            )
            system_message = system_message.replace(
                "{chat_history}", formatted_chat_history
            )
            system_message = system_message.replace(
                "{original_workout}", json.dumps(original_workout)
            )

        user_message = (
            "Create a new workout plan for a single day based on the given information."
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
        )
        new_workout = json.loads(response.choices[0].message.content)
        print(f"New workout plan generated for date: {date}")

        # Update the workout in the database
        gph.update_workout_by_date(week_id, date, new_workout)
        return new_workout

    except Exception as e:
        error_message = f"Error updating workout for date: {date} with error: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)
