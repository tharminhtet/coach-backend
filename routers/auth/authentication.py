from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from db.db_operations import DbOperations
from passlib.context import CryptContext 
from datetime import datetime, timedelta 
from jose import JWTError, jwt
from typing import Annotated
from enum import Enum
import uuid
import os
import re

load_dotenv()

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 1

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"

class CreateUserRequest(BaseModel):
    email: str
    password: str
    first_name: str or None = None
    last_name: str or None = None
    role: UserRole = UserRole.USER

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/register")
async def register(userProfile: CreateUserRequest):

    if not _is_valid_email(userProfile.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not a proper email address."
        )

    db_ops = DbOperations("user-profiles")
    try: 
        existing_user = db_ops.read_one_from_mongodb({"email": userProfile.email})
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reading given email from database: {str(e)}"
        )
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )

    new_user = {
        "user_id": f"{uuid.uuid4()}",
        "email": userProfile.email,
        "first_name": userProfile.first_name,
        "last_name": userProfile.last_name,
        "hashed_password": pwd_context.hash(userProfile.password),
        "role": userProfile.role
    }
    try:
        db_ops.write_to_mongodb(new_user)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error saving user login profile while registering: {str(e)}"
        )
    
    return {"status": "success", "message": "User registered successfully"}

@router.post("/token", response_model=Token)
async def login_access_for_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = _authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", 
                            headers={"WWW-Authenticate": "Bearer"})

    access_token_expires = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    access_token = _create_access_token(user["email"], user["role"], expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/getUser")
async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[ALGORITHM])
        email: str = payload.get('sub')
        role: str = payload.get('role')
        if email is None or role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user", 
                            headers={"WWW-Authenticate": "Bearer"})
        return {'email': email, 'role': role}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user", 
                            headers={"WWW-Authenticate": "Bearer"})

def _create_access_token(email: str, role: str, expires_delta: timedelta):
    encode = {'sub': email, 'role': role}
    # if expires_delta is provided, add that to current time else set it as 15 minutes
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=1440)
    encode.update({'exp': expire})
    return jwt.encode(encode, os.getenv("SECRET_KEY"), algorithm=ALGORITHM)

def _authenticate_user(email: str, password: str):

    db_ops = DbOperations("user-profiles")
    user = db_ops.read_one_from_mongodb({"email": email})
    if not user:
        return False
    if not pwd_context.verify(password, user['hashed_password']):
        return False
    
    return user

def _is_valid_email(email: str):

    """Check if the email is a valid format."""
    regex = r'^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w+$'
    return re.match(regex, email)
