from db.db_operations import DbOperations
from fastapi import HTTPException
from datetime import datetime, timedelta
import uuid
import json
import logging
import traceback
from services.onboarding_assistant import OnboardingAssistant
from enums import ChatPurpose
from openai import OpenAI
from typing import Optional

logger = logging.getLogger(__name__)


def _validate_generate_weekly_plan(user_id: str, start_date: str, year: str) -> bool:
    """
    Check if user weekly training plan is already generated for given start_date.
    """
    training_plans = _get_training_plan(user_id)
    start_date_set = set()
    for week_number in training_plans["training_plan"][year].keys():
        start_date_set.add(
            training_plans["training_plan"][year][week_number]["start_date"]
        )

    return start_date not in start_date_set


def _extract_user_data(
    user_id: str, chat_id: str | None = None
) -> list[dict[str, str]]:
    """
    Retrieve user data from chat if chat_id is provided else from user-details collection.
    """
    user_details_dboperations = DbOperations("user-details")
    if chat_id:
        # Onboard first-time user. Summarize assessment conversation.
        chat_history = _get_chat_history(chat_id, True)
        client = OpenAI()
        assistant = OnboardingAssistant(client)
        user_data = assistant.summarize(chat_history)
    else:
        try:
            user_data = user_details_dboperations.read_from_mongodb(query_param=user_id)
            if not user_data:
                error_message = "User data not found for user_id: " + user_id
                logger.error(error_message)
                logger.error(traceback.format_exc())
                raise HTTPException(status_code=404, detail=error_message)
            logger.info("Successfully retrieved user data.")
        except HTTPException as he:
            raise he
        except Exception as e:
            error_message = (
                f"Error reading user data for user_id: {user_id} from MongoDB: {e}"
            )
            logger.error(error_message)
            logger.error(traceback.format_exc())
            return {"status": "error", "message": error_message}, 500

        for data in user_data:
            data.pop("_id", None)

    # Remove memories field before returning
    for data in user_data:
        data.pop("memories", None)

    return user_data

def _extract_user_memories(user_id: str) -> Optional[list[str]]:
    """
    Retrieve user memories from user-details collection.
    """
    user_details_dboperations = DbOperations("user-details")
    try:
        user_data = user_details_dboperations.read_from_mongodb(query_param=user_id)
        if not user_data:
            logger.warning(f"User data not found for user_id: {user_id}")
            return None
        return user_data[0].get("memories", [])
    except Exception as e:
        error_message = f"Error reading user memories for user_id: {user_id} from MongoDB: {e}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return None


def _get_all_old_weekly_training_plans(user_id: str, year: str) -> list[dict[str, str]]:
    """
    Retrieve and return the fitness plans of all the past weeks.
    """
    # TODO: this will need to be updated to traverse through all the previous years
    training_plans = _get_training_plan(user_id)

    # get all the week_ids and retrieve all the fitness plans based on week_ids
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
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)
    return old_weekly_training_plans


def _save_new_weekly_training_plan(
    user_id: str, fitness_plan: dict, start_of_week: str
) -> str:
    """
    Save the newly generated weekly training plan in weekly-training-plans collection and return week_id
    """
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    week_id = f"{uuid.uuid4()}"
    fitness_plan["week_id"] = week_id
    fitness_plan["start_date"] = start_of_week
    fitness_plan["user_id"] = user_id
    try:
        weekly_plan_dboperations.write_to_mongodb(fitness_plan)
    except Exception as e:
        error_message = (
            f"Error saving in weekly-training-plans collection "
            f"for week_id: {week_id} with the error: {e}"
        )
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500
    logger.info(
        "Weekly training plan is successfully saved in weekly training plan db."
    )
    return week_id


def _update_overall_training_plan(
    user_id: str, week_id: str, week_number: int, start_of_week: str, year: str
) -> None:
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
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500
    logger.info(
        "Weekly training plan is successfully updated from user training plans."
    )


def _get_chat_history(
    chat_id: str, is_remove_system_message: bool
) -> tuple[list[dict[str, str]], Optional[str], Optional[dict]]:
    """
    Retrieve chat history from the database.
    Cleanup from chat history.
    Return empty list if chat_id is not found.
    Also return purpose and purpose_data.
    """
    db_operations = DbOperations("chat-history")
    chat_document = db_operations.collection.find_one({"chat_id": chat_id})
    messages = []
    purpose = None
    purpose_data = None
    if chat_document and "messages" in chat_document:
        messages = chat_document["messages"]
        purpose = chat_document.get("purpose")
        purpose_data = chat_document.get("purpose_data")
        if is_remove_system_message:
            messages = _cleanup_chat_history(chat_document)
        return (
            [{"role": m["role"], "content": m["content"]} for m in messages],
            purpose,
            purpose_data,
        )
    return messages, purpose, purpose_data


def _cleanup_chat_history(chat_document: dict):
    """
    Always remove the first message if it's a system message.
    Remove the first user message if the purpose is "workout_journal".
    """
    messages = chat_document.get("messages", [])

    # Always remove the first message if it's a system message
    if messages and messages[0]["role"] == "system":
        messages.pop(0)

    # Remove the first user message if the purpose is "workout_journal"
    if chat_document.get("purpose") == ChatPurpose.WORKOUT_JOURNAL.value:
        first_user_index = next(
            (i for i, m in enumerate(messages) if m["role"] == "user"), None
        )
        if first_user_index is not None:
            messages.pop(first_user_index)

    return messages


def _get_daily_training_plan(week_id: str, date: str):
    """
    Get daily training_plan based on week_id and given date.
    """
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    date_query = {"week_id": week_id, "workouts.date": date}
    projection = {
        "workouts.$": 1  # to return only the matching element in the workouts array
    }
    daily_plan = None
    try:
        result = weekly_plan_dboperations.read_one_from_mongodb_with_projection(
            date_query, projection
        )
        if not result:
            error_message = f"No workout found for date: {date}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)
        daily_plan = result["workouts"][0]
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = (
            f"Error reading weekly training plan for date: {date} with error: {str(e)}"
        )
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)
    logger.info(
        f"Successfully retrieved training_plan for week_id: {week_id} with date: {date}"
    )
    return daily_plan


def _get_weekly_training_plan(week_id: str):
    """
    Get weekly training_plan based on week_id.
    """
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    weekly_plan = None
    try:
        weekly_plan_query = {"week_id": week_id}
        weekly_plan = weekly_plan_dboperations.read_one_from_mongodb(weekly_plan_query)
        if not weekly_plan:
            error_message = "Weekly training plan not found"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f"Error retrieving weekly training plan: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)

    # Remove the _id field from the response
    if weekly_plan["_id"]:
        weekly_plan.pop("_id", None)

    logger.info(f"Successfully retrieved weekly training plan for week_id: {week_id}")
    return weekly_plan


def _get_training_plan(user_id: str):
    """
    Get training_plan based on user_id.
    """
    training_plan_dboperations = DbOperations("training-plans")
    training_plans = None
    try:
        plan_query = {"user_id": user_id}
        training_plans = training_plan_dboperations.read_one_from_mongodb(plan_query)
        if not training_plans:
            error_message = f"Training plan not found for the user: {user_id} as it may have never been created with user-details."
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = (
            f"Error retrieving training plan for user: {user_id} with error: {str(e)}"
        )
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)
    logger.info(f"Successfully retrieved training_plan for user_id: {user_id}")
    return training_plans


async def _get_weekly_training_plan_internal(target_date: datetime, user_id: str):
    """
    Internal function to get weekly training plan for a given date and user_id.
    """
    # Retrieve the training plan for the user
    training_plan = _get_training_plan(user_id)

    # Find the correct week for the given date
    year = str(target_date.year)
    if year not in training_plan["training_plan"]:
        error_message = "No training plan found for the specified year"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=404, detail=error_message)

    week_id = None
    for _, week_data in training_plan["training_plan"][year].items():
        week_start = datetime.strptime(week_data["start_date"], "%Y-%m-%d")
        week_end = week_start + timedelta(days=6)
        if week_start <= target_date <= week_end:
            week_id = week_data["week_id"]
            break
    if not week_id:
        return None

    # Retrieve the weekly training plan
    weekly_plan = _get_weekly_training_plan(week_id)
    return weekly_plan


def get_workout_by_date(week_id: str, date: str) -> dict:
    """
    Retrieve the workout plan for a specific date within a given week.
    """
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    query = {"week_id": week_id, "workouts.date": date}
    projection = {"workouts.$": 1}

    try:
        result = weekly_plan_dboperations.read_one_from_mongodb_with_projection(
            query, projection
        )
        if result and "workouts" in result and len(result["workouts"]) > 0:
            return result["workouts"][0]
        else:
            error_message = (
                f"No workout plan found for week_id: {week_id} and date: {date}"
            )
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f"Error retrieving workout for week_id: {week_id} and date: {date}. Error: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)


def update_workout_by_date(week_id: str, date: str, new_workout: dict):
    """
    Update with new_workout based on given week_id and date.
    """
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    update_query = {
        "$set": {
            "workouts.$.exercises": new_workout["exercises"],
            "workouts.$.reasoning": new_workout["reasoning"],
        }
    }
    match_query = {"week_id": week_id, "workouts.date": date}

    try:
        existing_workout = weekly_plan_dboperations.read_one_from_mongodb(match_query)
        if not existing_workout:
            error_message = f"No workout found for week_id: {week_id} and date: {date}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)
        weekly_plan_dboperations.update_from_mongodb(match_query, update_query)
    except Exception as e:
        error_message = f"Error updating workout for date: {date} in week_id: {week_id}. Error: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)


def update_weekly_summary(user_id: str):
    """
    Update weekly summary of the last week.
    """
    training_plans = _get_training_plan(user_id)
    year = str(datetime.now().year)

    # if exist, get the latest week and update that week training plan summary
    if training_plans:
        week_keys = training_plans["training_plan"][year].keys()
        if week_keys:
            most_recent_week = sorted(week_keys)[-1]
            week_id = training_plans["training_plan"][year][most_recent_week]["week_id"]

            most_recent_week_plan = _get_weekly_training_plan(week_id)
            client = OpenAI()
            with open("prompts/weekly_plan_summary.txt", "r") as file:
                system_message = file.read()
                system_message = system_message.replace(
                    "most_recent_week_plan", json.dumps(most_recent_week_plan)
                )
            user_message = "Create the summary of the last week training plan."

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
            )
            response = response.choices[0].message.content
            new_value = {
                "$set": {f"training_plan.{year}.{most_recent_week}.summary": response}
            }
            training_plan_dboperations = DbOperations("training-plans")
            plan_query = {"user_id": user_id}
            try:
                training_plan_dboperations.update_from_mongodb(plan_query, new_value)
            except Exception as e:
                error_message = (
                    f"Error updating training summary of training plan "
                    f"for week_id: {week_id} in MongoDB: {str(e)}"
                )
                logger.error(error_message)
                logger.error(traceback.format_exc())
                raise HTTPException(status_code=500, detail=error_message)


def _update_or_insert_workout_for_specific_date(
    week_id: str, date: str, new_workout: dict, shouldReplace: bool
):
    weekly_plan_dboperations = DbOperations("weekly-training-plans")
    query = {"week_id": week_id, "workouts.date": date}

    existing_workout = weekly_plan_dboperations.read_one_from_mongodb(query)

    if existing_workout:
        # Replace existing workout
        if shouldReplace:
            update_query = {"$set": {"workouts.$": new_workout}}
        # Add all user workouts to generated plan
        else:
            update_query = {
                "$push": {"workouts.$.exercises": {"$each": new_workout["exercises"]}}
            }
        weekly_plan_dboperations.update_from_mongodb(query, update_query)
    else:
        # Insert new workout
        update_query = {"$push": {"workouts": new_workout}}
        weekly_plan_dboperations.update_from_mongodb({"week_id": week_id}, update_query)
