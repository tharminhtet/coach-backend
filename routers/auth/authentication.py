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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import uuid
import os
import re
import logging
import traceback
import secrets
import smtplib

load_dotenv()

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 1

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

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

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

@router.post("/register")
async def register(userProfile: CreateUserRequest):

    if not _is_valid_email(userProfile.email):
        error_message = "Not a proper email address."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_message
        )

    db_ops = DbOperations("user-profiles")
    try: 
        existing_user = db_ops.read_one_from_mongodb({"email": userProfile.email})
    except Exception as e:
        error_message = f"Error reading given email from database: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=error_message
        )
    
    if existing_user:
        error_message = "Email already exists."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_message
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
        error_message = f"Error saving user login profile while registering in MongoDB: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=error_message
        )
    
    return {"status": "success", "message": "User registered successfully"}

@router.post("/token", response_model=Token)
async def login_access_for_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = _authenticate_user(form_data.username, form_data.password)
    if not user:
        error_message = "Incorrect email or password."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_message, 
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
            error_message = "Could not validate user as email or role is empty."
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_message, 
                            headers={"WWW-Authenticate": "Bearer"})
        return {'email': email, 'role': role}
    except JWTError:
        error_message = "Could not validate user"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_message, 
                            headers={"WWW-Authenticate": "Bearer"})

@router.post("/reset-password-request")
async def reset_password_request(email: str):
    if not _is_valid_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email address"
        )
    
    db_ops = DbOperations("user-profiles")
    user = db_ops.read_one_from_mongodb({"email": email})
    if not user:
        # To prevent email enumeration, we'll return a success message even if the user doesn't exist
        return {"message": "There is no existing account associated with the email."}, 200
    
    reset_token = secrets.token_urlsafe(32)
    _store_reset_token(email, reset_token)
    
    reset_link = f"https://yourapp.com/reset-password?token={reset_token}"
    _send_reset_email(email, reset_link)
    
    return {"message": "A password reset link has been successfully sent."}, 200

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    token_data = _validate_reset_token(request.token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token."
        )
    
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )
    
    _update_user_password(token_data["email"], request.new_password)
    _delete_reset_token(request.token)
    
    return {"message": "Password has been reset successfully"}, 200

def _store_reset_token(email: str, token: str):
    expiration = datetime.utcnow() + timedelta(minutes=10)
    db_ops = DbOperations("password-reset-tokens")
    db_ops.write_to_mongodb({
        "email": email,
        "token": token,
        "expiration": expiration
    })

def _send_reset_email(email: str, reset_link: str):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SENDER_EMAIL")

    message = MIMEMultipart("alternative")
    message["Subject"] = "Password Reset Request"
    message["From"] = sender_email
    message["To"] = email

    text = f"""
    Hello,

    You have requested to reset your password. Please click on the link below to reset your password:

    {reset_link}

    If you did not request this, please ignore this email.

    This link will expire in 10 minutes.

    Best regards,
    Nirvana Coach
    """

    html = f"""
    <html>
    <body>
        <p>Hello,</p>
        <p>You have requested to reset your password. Please click on the link below to reset your password:</p>
        <p><a href="{reset_link}">{reset_link}</a></p>
        <p>If you did not request this, please ignore this email.</p>
        <p>This link will expire in 10 minutes.</p>
        <p>Best regards,<br>Nirvana Coach</p>
    </body>
    </html>
    """

    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")

    message.attach(part1)
    message.attach(part2)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()  # Can be omitted
            server.starttls()
            server.ehlo()  # Can be omitted
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, email, message.as_string())
        logger.info(f"Password reset email sent to {email}")
    except Exception as e:
        error_message = f"Failed to send password reset email to {email}: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to send password reset email")

def _validate_reset_token(token: str):
    db_ops = DbOperations("password-reset-tokens")
    token_data = db_ops.read_one_from_mongodb({"token": token})
    if not token_data or token_data["expiration"] < datetime.utcnow():
        return None
    return token_data

def _update_user_password(email: str, new_password: str):
    db_ops = DbOperations("user-profiles")
    hashed_password = pwd_context.hash(new_password)
    db_ops.update_from_mongodb(
        {"email": email},
        {"$set": {"hashed_password": hashed_password}}
    )

def _delete_reset_token(token: str):
    db_ops = DbOperations("password-reset-tokens")
    db_ops.delete_one_from_mongodb({"token": token})

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
