from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from db_operations import DbOperations
from passlib.context import CryptContext

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserProfile(BaseModel):
    username: str
    password: str

@router.post("/register")
async def register(userProfile: UserProfile):

    db_ops = DbOperations("user-profiles")
    try: 
        existing_user = db_ops.read_one_from_mongodb({"username": userProfile.username})
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reading given username from database: {str(e)}"
        )
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    new_user = {
        "username": userProfile.username,
        "password": pwd_context.hash(userProfile.password)
    }
    try:
        db_ops.write_to_mongodb(new_user)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error saving user login profile while registering: {str(e)}"
        )
    
    return {"status": "success", "message": "User registered successfully"}

@router.post("/login")
async def login(userProfile: UserProfile):
    
    db_ops = DbOperations("user-profiles")
    try: 
        user = db_ops.read_one_from_mongodb({"username": userProfile.username})
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reading given username from database: {str(e)}"
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username."
        )
    
    # Verify password
    if not pwd_context.verify(userProfile.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password"
        )
    
    return {"status": "success", "message": "Logged in successfully"}