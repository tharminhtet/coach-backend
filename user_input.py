from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from db_operations import DbOperations
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
        dboperations = DbOperations("user-details")
        data = request.dict()
        user_id = f"{uuid.uuid4()}"
        data["user_id"] = user_id
        dboperations.write_to_mongodb(data)
        print("Successfully uploaded user data.")
    except Exception as e:
        print(f"Error writing to MongoDB: {e}")
