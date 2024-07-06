from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from db_operations import DbOperations
from datetime import datetime
import enum
import uuid

router = APIRouter()

# class FitnessLevel(enum.Enum):
#     BEGINNER = 1
#     INTERMEDIATE = 2
#     PROFESSIONAL = 3

class UserStats(BaseModel):
    availableDays: int # how many days a person can workout
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
async def uploadUserDetails(request: Request):
    """
    Upload user's information.
    """

    try:
        # write user information into db
        user_details = request.dict()
        user_id = f"{uuid.uuid4()}"
        user_details["user_id"] = user_id
        user_dboperations = DbOperations("user-details")
        user_dboperations.write_to_mongodb(user_details)

        # write a skeleton schema of user training plan without any plan details into db
        training_plan_id = f"{uuid.uuid4()}"
        training_plan = {"user_id": user_id}
        training_plan["training_plan"] = {}
        year = datetime.now().year
        training_plan["training_plan"][str(year)] = {}
        training_plan["training_plan"]["summary"] = ""
        training_plan_dboperations = DbOperations("training-plans")
        training_plan_dboperations.write_to_mongodb(training_plan)
        print("Successfully uploaded user data and stored the skeleton schema for user training plan.")
    except Exception as e:
        print(f"Error writing to MongoDB: {e}")
