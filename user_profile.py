from fastapi import APIRouter, HTTPException
from db_operations import DbOperations

router = APIRouter()

@router.get("/get_user_id")
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

async def get_user_id_internal(username: str):
    user_profile = await get_user_id(username)
    return user_profile["user_id"]