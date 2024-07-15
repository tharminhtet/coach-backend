# from fastapi import Depends, HTTPException, status
# from fastapi.security import OAuth2PasswordBearer
# from jose import jwt
# from typing import List
# from enum import Enum
# import os

# from authentication import get_current_user, ALGORITHM

# oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")

# class UserRole(str, Enum):
#     ADMIN = "admin"
#     USER = "user"

# def RoleChecker(allowed_roles: List[UserRole]):
#     async def check_role(token: str = Depends(oauth2_bearer)):
#         try:
#             payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[ALGORITHM])
#             user_role: str = payload.get("role")
#             if user_role not in allowed_roles:
#                 raise HTTPException(
#                     status_code=status.HTTP_403_FORBIDDEN,
#                     detail="You don't have permission to access this resource"
#                 )
#         except jwt.JWTError:
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Could not validate credentials",
#                 headers={"WWW-Authenticate": "Bearer"},
#             )
#     return check_role

# admin_required = RoleChecker([UserRole.ADMIN])
# user_or_admin_required = RoleChecker([UserRole.USER, UserRole.ADMIN])

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import List
from enum import Enum

from authentication import get_current_user

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"

def RoleChecker(allowed_roles: List[UserRole]):
    async def check_role(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this resource"
            )
        return current_user
    return check_role

admin_required = RoleChecker([UserRole.ADMIN])
user_or_admin_required = RoleChecker([UserRole.USER, UserRole.ADMIN])