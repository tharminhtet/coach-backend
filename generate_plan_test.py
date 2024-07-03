from dotenv import load_dotenv
from fastapi import APIRouter
from db_operations import DbOperations
from openai import OpenAI
import os
import json
import uuid

# Load .env file
load_dotenv()

router = APIRouter()

@router.get("/getPlans")
async def generatePlan(user_id: str):
    user_training_plan_dboperations = DbOperations("training-plans")
    try:
        previous_user_training_plans = user_training_plan_dboperations.read_from_mongodb(query_param=user_id, sort_param="week", sort_order=-1)
        print("Successfully retrieved user's previous training plan.")
    except Exception as e:
        print(f"Error reading previous training plab from MongoDB: {e}")
    
    if len(previous_user_training_plans) == 0:
        previous_user_training_plans = {}
    else:
        for data in previous_user_training_plans:
            data.pop("_id", None)
        
    return previous_user_training_plans

@router.get("/generatePlan")
async def generatePlan(user_id: str):
    user_details_dboperations = DbOperations("user-details")
    try:
        user_data = user_details_dboperations.read_from_mongodb(query_param=user_id)
        print("Successfully retrieved user data.")
    except Exception as e:
        print(f"Error reading user data from MongoDB: {e}")

    for data in user_data:
        data.pop("_id", None)

    user_training_plan_dboperations = DbOperations("training-plans")
    try:
        previous_user_training_plans = user_training_plan_dboperations.read_from_mongodb(query_param=user_id, sort_param="week", sort_order=-1)
        print("Successfully retrieved user's previous training plan.")
    except Exception as e:
        print(f"Error reading previous training plab from MongoDB: {e}")
    
    if len(previous_user_training_plans) == 0:
        previous_user_training_plans = {}
    else:
        for data in previous_user_training_plans:
            data.pop("_id", None)
        previous_user_training_plans = previous_user_training_plans[0]
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    with open("prompts/generate_fitness_plan_system_message.txt", "r") as file:
        system_message = file.read()
        system_message = system_message.replace("{user_data}", json.dumps(user_data))
        system_message = system_message.replace("{previous_week_training_plan}", json.dumps(previous_user_training_plans))
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
    # print(response)
    fitness_plan = json.loads(response)
    fitness_plan["user_id"] = user_id
    fitness_plan_id = f"{uuid.uuid4()}"
    fitness_plan["fitness_plan_id"] = fitness_plan_id
    try:
        user_training_plan_dboperations.write_to_mongodb(fitness_plan)
        print("Successfully stored new training plan.")
    except Exception as e:
        print(f"Error writing to MongoDB: {e}")
    
    # print(fitness_plan)

    return json.loads(response)
