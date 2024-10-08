from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Union, Dict, Any
from datetime import datetime
from db.db_operations import DbOperations
from authorization import user_or_admin_required
from enum import Enum
import logging
import traceback

router = APIRouter(prefix="/user", tags=["user_profile"])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FitnessLevel(str, Enum):
    BEGINNER = "Beginner (You're new to fitness and want to learn the basics)"
    NOVICE = "Novice (You have some experience but are still learning)"
    INTERMEDIATE = "Intermediate (You're comfortable with most exercises and have been training regularly)"
    ADVANCED = "Advanced (You have significant experience and are looking to optimize your training)"
    ATHLETE = "Athlete (You train at a competitive level)"


class UserProfile(BaseModel):
    personalInfo: Dict[str, Union[str, int, float]]
    fitnessProfile: Dict[str, Union[str, List[str]]]
    healthInfo: Dict[str, Union[str, List[str]]]
    lifestyle: Dict[str, Union[str, List[str]]]


class Request(BaseModel):
    userProfile: UserProfile


class UpdateUserDetailsRequest(BaseModel):
    user_details_field: str
    value: Union[int, str, List[str], FitnessLevel]


@router.post("/uploadUserDetails")
async def uploadUserDetails(
    request: Request, current_user: dict = Depends(user_or_admin_required)
):
    """
    Upload user's information, equipment, goal and available dates.
    """

    user_id = await get_user_id_internal(current_user["email"])
    # write user details into db
    try:
        user_details = request.model_dump()
        user_details["user_id"] = user_id

        if _validate_user_details(user_id):
            error_message = (
                f'The user details already exist for username: {current_user["email"]}'
            )
            logger.error(error_message)
            logger.error(traceback.format_exc())
            return {"status": "error", "message": error_message}, 400

        user_dboperations = DbOperations("user-details")
        user_dboperations.write_to_mongodb(user_details)
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f'Error writing user-details for {current_user["email"]} in MongoDB: {str(e)}'
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500

    # write a skeleton schema of user training plan without any plan details into db
    try:
        training_plan = {"user_id": user_id}
        training_plan["training_plan"] = {}
        year = datetime.now().year
        training_plan["training_plan"][str(year)] = {}
        training_plan["training_plan"]["summary"] = ""
        training_plan_dboperations = DbOperations("training-plans")
        training_plan_dboperations.write_to_mongodb(training_plan)
        logger.info(
            "Successfully uploaded user data and stored the skeleton schema for user training plan."
        )
        return {
            "status": "success",
            "message": "User details uploaded successfully",
        }, 200
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f'Error creating skeleton training plan for {current_user["email"]} in MongoDB: {str(e)}'
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500


@router.post("/initiateUserDetails")
async def initiateUserDetails(current_user: dict = Depends(user_or_admin_required)):
    """
    Create a skeleton schema of user-details and training plan with empty values.
    """
    user_id = await get_user_id_internal(current_user["email"])

    try:
        if _validate_user_details(user_id):
            error_message = (
                f'User details already exist for username: {current_user["email"]}'
            )
            logger.error(error_message)
            return {"status": "error", "message": error_message}, 400

        # Create skeleton user details
        user_details = {
            "user_id": user_id,
            "personalInfo": {
                "name": None,
                "gender": None,
                "age": None,
                "height": None,
                "weight": None,
                "bodyType": None,
            },
            "fitnessProfile": {
                "fitnessLevel": None,
                "fitnessGoal": [],
                "currentActivities": [],
                "cardioPreference": None,
            },
            "healthInfo": {
                "injuries": [],
                "otherHealthConstraints": None,
                "dietaryPreferences": [],
            },
            "lifestyle": {
                "trainingLocation": [],
                "gymType": [],
                "workoutTime": [],
                "workoutDays": [],
                "workoutDuration": None,
                "availableDays": None,
            },
        }

        user_dboperations = DbOperations("user-details")
        user_dboperations.write_to_mongodb(user_details)

        # Create skeleton training plan
        training_plan = {
            "user_id": user_id,
            "training_plan": {str(datetime.now().year): {}, "summary": ""},
        }

        training_plan_dboperations = DbOperations("training-plans")
        training_plan_dboperations.write_to_mongodb(training_plan)

        logger.info(
            f"Successfully initiated user details and training plan for user_id: {user_id}"
        )
        return {
            "status": "success",
            "message": "User details and training plan skeletons created successfully",
        }, 200
    except Exception as e:
        error_message = f'Error initiating user data for {current_user["email"]} in MongoDB: {str(e)}'
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500


@router.put("/updateUserDetails")
async def update_user_details(
    request: UpdateUserDetailsRequest,
    current_user: dict = Depends(user_or_admin_required),
):
    """
    Update specific user details field for current user.
    """
    user_id = await get_user_id_internal(current_user["email"])
    user_dboperations = DbOperations("user-details")

    print(request)
    try:
        _validate_update_user_details(request.user_details_field, request.value)
        update_query = {"$set": {request.user_details_field: request.value}}
        result = user_dboperations.update_from_mongodb(
            {"user_id": user_id}, update_query
        )

        if result.modified_count == 0:
            error_message = "User details not found or no changes is made"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)

        return {
            "status": "success",
            "message": f"User detail {request.user_details_field} is updated successfully",
        }, 200

    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f'Error updating user details for {current_user["email"]} in MongoDB: {str(e)}'
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500


@router.get("/getUserDetails")
async def get_user_details(current_user: dict = Depends(user_or_admin_required)):
    """
    Retrieve user details for the current user.
    """
    user_id = await get_user_id_internal(current_user["email"])
    user_dboperations = DbOperations("user-details")

    try:
        user_details = user_dboperations.read_one_from_mongodb({"user_id": user_id})
        if not user_details:
            error_message = f"User details not found for user_id: {user_id}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)

        # Remove the _id field from the response
        user_details.pop("_id", None)
        return user_details

    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f'Error retrieving user details for {current_user["email"]} from MongoDB: {str(e)}'
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)


@router.get("/getUserId")
async def get_user_id(username: str = None):

    user_profiles_db = DbOperations("user-profiles")
    try:
        user_profile = user_profiles_db.read_one_from_mongodb({"email": username})
        if not user_profile:
            error_message = f"User profile is not found"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=404, detail=error_message)
        logger.info("Successfully retrieved user data.")

        return {"user_id": user_profile["user_id"]}
    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = f"Error reading user_id for {username} in MongoDB: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500


@router.delete("/deleteUserProfile")
async def delete_user_profile(current_user: dict = Depends(user_or_admin_required)):
    """
    Delete everything associated with given user_id:
    user_profile, user_details, training_plan, weekly_traning_plan, and chat_history
    """
    user_id = await get_user_id_internal(current_user["email"])
    query = {"user_id": user_id}

    collections = [
        ("user-profiles", "read_one_from_mongodb")
        # ("user-details", "read_one_from_mongodb"),
        # ("training-plans", "read_one_from_mongodb")
    ]

    # Check if user exists in all collections
    for collection, read_method in collections:
        db_operations = DbOperations(collection)
        try:
            result = getattr(db_operations, read_method)(query)
            if not result:
                error_message = f"User with id {user_id} not found in {collection}"
                logger.error(error_message)
                logger.error(traceback.format_exc())
                raise HTTPException(status_code=404, detail=error_message)
        except HTTPException as he:
            raise he
        except Exception as e:
            error_message = f"Error checking {collection}: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)

    # Delete if user exists in all collections
    delete_operations = [
        ("weekly-training-plans", "delete_many_from_mongodb"),
        ("training-plans", "delete_one_from_mongodb"),
        ("user-details", "delete_one_from_mongodb"),
        ("user-profiles", "delete_one_from_mongodb"),
        ("chat-history", "delete_many_from_mongodb"),
    ]

    for collection, delete_method in delete_operations:
        db_operations = DbOperations(collection)
        try:
            getattr(db_operations, delete_method)(query)
        except Exception as e:
            error_message = f"Error deleting from {collection} collection for user_id: {user_id} with the error: {e}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)

    return {
        "status": "success",
        "message": "User profile and associated data successfully deleted.",
    }


@router.get("/verifyUserDetails")
async def verify_user_details(current_user: dict = Depends(user_or_admin_required)):
    """
    Verify if all required fields in the user-details collection are populated.
    """
    user_id = await get_user_id_internal(current_user["email"])
    user_dboperations = DbOperations("user-details")

    try:
        user_details = user_dboperations.read_one_from_mongodb({"user_id": user_id})
        if not user_details:
            raise HTTPException(status_code=404, detail="User details not found")

        required_fields = [
            "personalInfo.name",
            "personalInfo.gender",
            "personalInfo.age",
            "personalInfo.height",
            "personalInfo.weight",
            "personalInfo.bodyType",
            "fitnessProfile.fitnessLevel",
            "fitnessProfile.fitnessGoal",
            "fitnessProfile.currentActivities",
            "fitnessProfile.cardioPreference",
            "lifestyle.trainingLocation",
            "lifestyle.gymType",
            "lifestyle.workoutTime",
            "lifestyle.workoutDays",
            "lifestyle.workoutDuration",
            "lifestyle.availableDays",
        ]

        missing_fields = [
            field
            for field in required_fields
            if not _get_nested_value(user_details, field)
        ]

        return {
            "isComplete": len(missing_fields) == 0,
            "missing_fields": missing_fields if missing_fields else None,
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        error_message = (
            f'Error verifying user details for {current_user["email"]}: {str(e)}'
        )
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)


async def get_user_id_internal(username: str):
    user_profile = await get_user_id(username)
    return user_profile["user_id"]


def _validate_update_user_details(
    user_details_field: str, value: Union[int, str, List[str], FitnessLevel]
):
    """
    Validate if user_details_field and its value is valid type.
    """
    valid_fields = [
        "personalInfo.name",
        "personalInfo.gender",
        "personalInfo.age",
        "personalInfo.height",
        "personalInfo.weight",
        "personalInfo.bodyType",
        "fitnessProfile.fitnessLevel",
        "fitnessProfile.fitnessGoal",
        "fitnessProfile.currentActivities",
        "fitnessProfile.cardioPreference",
        "healthInfo.injuries",
        "healthInfo.otherHealthConstraints",
        "healthInfo.dietaryPreferences",
        "lifestyle.trainingLocation",
        "lifestyle.gymType",
        "lifestyle.workoutTime",
        "lifestyle.workoutDays",
        "lifestyle.workoutDuration",
        "lifestyle.availableDays",
    ]
    if user_details_field not in valid_fields:
        error_message = "Invalid user_details_field."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=error_message)

    # Additional validation for FitnessLevel
    if user_details_field == "fitnessProfile.fitnessLevel":
        try:
            FitnessLevel(value)
        except ValueError:
            error_message = f"Invalid fitness level. Valid levels are: {', '.join([level.value for level in FitnessLevel])}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=400, detail=error_message)

    list_fields = [
        "fitnessProfile.fitnessGoal",
        "fitnessProfile.currentActivities",
        "healthInfo.injuries",
        "healthInfo.dietaryPreferences",
        "lifestyle.trainingLocation",
        "lifestyle.gymType",
        "lifestyle.workoutTime",
        "lifestyle.workoutDays",
    ]

    if user_details_field in list_fields and not isinstance(value, list):
        error_message = f"{user_details_field} must be a list of strings."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=error_message)

    if user_details_field in list_fields and not all(
        isinstance(item, str) for item in value
    ):
        error_message = f"All items in {user_details_field} must be strings."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=error_message)

    string_fields = [
        "personalInfo.name",
        "personalInfo.gender",
        "personalInfo.bodyType",
        "fitnessProfile.cardioPreference",
        "healthInfo.otherHealthConstraints",
        "lifestyle.workoutDuration",
    ]
    if user_details_field in string_fields and not isinstance(value, str):
        error_message = f"{user_details_field} must be a string."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=error_message)


def _validate_user_details(user_id: str):
    """
    Check if user details for given user_id already exists
    """
    user_details_dboperations = DbOperations("user-details")
    user_details = None
    try:
        query = {"user_id": user_id}
        user_details = user_details_dboperations.read_one_from_mongodb(query)

    except Exception as e:
        error_message = f"Error reading from user-details collection for user: {user_id} with the error: {e}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_message}, 500

    return user_details is not None


def _get_nested_value(data: Dict[str, Any], key: str) -> Any:
    """
    Get a nested value from a dictionary using a dot-separated key.
    """
    keys = key.split(".")
    for k in keys:
        if isinstance(data, dict):
            data = data.get(k)
        else:
            return None
    return data
