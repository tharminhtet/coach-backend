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
from db.db_operations import DbOperations

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


class DeleteExerciseRequest(BaseModel):
    week_id: str
    date: str
    exercise_index: int


@router.delete("/deleteExercise")
async def delete_exercise(
    request: DeleteExerciseRequest, current_user: dict = Depends(user_or_admin_required)
):
    """
    Delete a single exercise from a workout for a specific date in a weekly plan.
    """
    try:
        weekly_plan_dboperations = DbOperations("weekly-training-plans")

        # Fetch the weekly plan
        weekly_plan = weekly_plan_dboperations.read_one_from_mongodb(
            {"week_id": request.week_id}
        )

        if not weekly_plan:
            raise HTTPException(status_code=404, detail="Weekly plan not found")

        # Find the workout for the specified date
        workout = next(
            (w for w in weekly_plan["workouts"] if w["date"] == request.date), None
        )

        if not workout:
            raise HTTPException(
                status_code=404, detail="Workout not found for the specified date"
            )

        # Check if the exercise index is valid
        if request.exercise_index < 0 or request.exercise_index >= len(
            workout["exercises"]
        ):
            raise HTTPException(status_code=400, detail="Invalid exercise index")

        # Remove the exercise
        del workout["exercises"][request.exercise_index]

        # Update the weekly plan in the database
        result = weekly_plan_dboperations.update_from_mongodb(
            {"week_id": request.week_id},
            {"$set": {"workouts": weekly_plan["workouts"]}},
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=404, detail="Failed to update the weekly plan"
            )

        logger.info(
            f"Exercise deleted from workout on {request.date} in week {request.week_id}"
        )
        return {
            "message": "Exercise deleted successfully",
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f"Error deleting exercise: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)
