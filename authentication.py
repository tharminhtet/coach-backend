from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from db_operations import DbOperations
from passlib.context import CryptContext 
from datetime import datetime, timedelta 
from jose import JWTError, jwt
from typing import Annotated
import os

load_dotenv()

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: str or None = None
    full_name: str or None = None 

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/register")
async def register(userProfile: CreateUserRequest):

    db_ops = DbOperations("user-profiles")
    try: 
        existing_user = db_ops.read_one_from_mongodb({userProfile.username: {'$exists': True}})
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
        userProfile.username: {
            "username": userProfile.username,
            "full_name": userProfile.full_name,
            "email": userProfile.email,
            "hashed_password": pwd_context.hash(userProfile.password),
        }
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", 
                            headers={"WWW-Authenticate": "Bearer"})

    access_token_expires = timedelta(ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = _create_access_token(user["username"], expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/getToken")
async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[ALGORITHM])
        username: str = payload.get('sub')
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user", 
                            headers={"WWW-Authenticate": "Bearer"})
        return {'username': username}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate user", 
                            headers={"WWW-Authenticate": "Bearer"})

def _create_access_token(username: str, expires_delta: timedelta):
    encode = {'sub': username}
    # if expires_delta is provided, add that to current time else set it as 15 minutes
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    encode.update({'exp': expire})
    return jwt.encode(encode, os.getenv("SECRET_KEY"), algorithm=ALGORITHM)

def _authenticate_user(username: str, password: str):
    db_ops = DbOperations("user-profiles")
    user = db_ops.read_one_from_mongodb({username: {'$exists': True}})
    if not user:
        return False
    if not pwd_context.verify(password, user[username]['hashed_password']):
        return False
    
    return user[username]