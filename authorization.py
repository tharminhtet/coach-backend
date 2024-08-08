from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import List
from enum import Enum
from routers.auth.authentication import get_current_user
import logging
import traceback

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"

def RoleChecker(allowed_roles: List[UserRole]):
    async def check_role(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            error_message = "You don't have permission to access this resource"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=error_message
            )
        return current_user
    return check_role

admin_required = RoleChecker([UserRole.ADMIN])
user_or_admin_required = RoleChecker([UserRole.USER, UserRole.ADMIN])