from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from datetime import datetime
from db_operations import DbOperations
from authorization import user_or_admin_required
import enum

router = APIRouter(
    prefix='/user',
    tags=['user_profile']
)

# class FitnessLevel(enum.Enum):
#     BEGINNER = 1
#     INTERMEDIATE = 2
#     PROFESSIONAL = 3

class UserStats(BaseModel):
    availableDays: int # how many days a person can workout
    preferredDays: List[str] # which days a person would like to workout
    availableEquipments: List[str]
    fitnessLevel: str
    bodyWeight: int # kg 
    height: int # cm
    goal: List[str]
    constraint: List[str]

class Request(BaseModel):
    username: str
    age: int
    gender: str
    stats: UserStats

@router.post("/upload_user_details")
async def uploadUserDetails(request: Request, _: dict = Depends(user_or_admin_required)):
    """
    Upload user's information, equipment, goal and available dates.
    """

    try:
        # write user information into db
        user_details = request.model_dump()
        user_id = await get_user_id_internal(user_details["username"])
        user_details["user_id"] = user_id
        user_dboperations = DbOperations("user-details")
        user_dboperations.write_to_mongodb(user_details)

        # write a skeleton schema of user training plan without any plan details into db
        # training_plan_id = f"{uuid.uuid4()}"
        training_plan = {"user_id": user_id}
        training_plan["training_plan"] = {}
        year = datetime.now().year
        training_plan["training_plan"][str(year)] = {}
        training_plan["training_plan"]["summary"] = ""
        training_plan_dboperations = DbOperations("training-plans")
        training_plan_dboperations.write_to_mongodb(training_plan)
        print("Successfully uploaded user data and stored the skeleton schema for user training plan.")
        return {"status": "success", "message": "User details uploaded successfully"}, 200
    except Exception as e:
        print(f"Error writing to MongoDB: {e}")
        return {"status": "error", "message": str(e)}, 500

@router.get("/getUserId")
async def get_user_id(username: str = None):

    user_profiles_db = DbOperations("user-profiles")
    try:
        user_profile = user_profiles_db.read_one_from_mongodb({"email": username})
        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile is not found")
        print("Successfully retrieved user data.")

        return {"user_id": user_profile["user_id"]}
    except Exception as e:
        print(f"Error reading from MongoDB: {e}")
        return {"status": "error", "message": str(e)}, 500

@router.delete("/deleteUserProfile")
async def delete_user_profile(user_id: str, _: dict = Depends(user_or_admin_required)):
    """
    Delete everything associated with given user_id: 
    user_profile, user_details, training_plan, weekly_traning_plan
    """
    query = {"user_id": user_id}
    
    collections = [
        ("user-profiles", "read_one_from_mongodb"),
        ("user-details", "read_one_from_mongodb"),
        ("training-plans", "read_one_from_mongodb")
    ]

    # Check if user exists in all collections
    for collection, read_method in collections:
        db_operations = DbOperations(collection)
        try:
            result = getattr(db_operations, read_method)(query)
            if not result:
                raise HTTPException(status_code=404, detail=f"User with id {user_id} not found in {collection}")
        except HTTPException as he:
            raise he
        except Exception as e:
            print(f"Error checking {collection}: {e}")
            raise HTTPException(status_code=500, detail=f"Error checking {collection}: {str(e)}")

    # Delete if user exists in all collections
    delete_operations = [
        ("weekly-training-plans", "delete_many_from_mongodb"),
        ("training-plans", "delete_many_from_mongodb"),
        ("user-details", "delete_one_from_mongodb"),
        ("user-profiles", "delete_one_from_mongodb")
    ]

    for collection, delete_method in delete_operations:
        db_operations = DbOperations(collection)
        try:
            getattr(db_operations, delete_method)(query)
        except Exception as e:
            error_message = f"Error deleting from {collection} collection for user_id: {user_id} with the error: {e}"
            print(error_message)
            raise HTTPException(status_code=500, detail=error_message)

    return {
        "status": "success",
        "message": "User profile and associated data successfully deleted.",
    }

async def get_user_id_internal(username: str):
    user_profile = await get_user_id(username)
    return user_profile["user_id"]