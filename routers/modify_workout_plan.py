from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import json
from datetime import datetime
from openai import OpenAI
from authorization import user_or_admin_required
from routers.generate_plan import get_weekly_training_plan_api
from routers.helpers import generate_plan_helpers as gph
import logging
import traceback

router = APIRouter()
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


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
    with open("prompts/log_user_specified_workout_system_message.txt", "r") as file:
        system_message = file.read()
    with open("prompts/log_user_specified_workout_user_message.txt", "r") as file:
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
    for exercise in workout_log["exercises"]:
        exercise["coach_note"] = (
            "Manually logged by user. Not part of the coach's workout plan."
        )
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
