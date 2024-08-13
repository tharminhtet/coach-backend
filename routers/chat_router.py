from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Union
from db.db_operations import DbOperations
from authorization import user_or_admin_required
from datetime import datetime, time
import uuid
from services.onboarding_assistant import OnboardingAssistant, OnboardingPurposeData
from services.workout_journal_assistant import (
    WorkoutJournalAssistant,
    WorkoutJournalPurposeData,
)
from services.workout_guide_assistant import (
    WorkoutGuideAssistant,
    WorkoutGuidePurposeData,
)
from openai import OpenAI
import logging
import traceback
import json
from enum import Enum
from routers.user_profile import get_user_id_internal

router = APIRouter()
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    content: str
    role: str
    timestamp: datetime


class ChatPurpose(Enum):
    WORKOUT_GUIDE = "workout_guide"
    WORKOUT_JOURNAL = "workout_journal"
    ONBOARDING = "onboarding"
    GENERAL = "general"


class BaseChatRequest(BaseModel):
    message: str = Field(..., description="The message content sent by the user")
    purpose: ChatPurpose = Field(
        ..., description="The purpose or context of the chat message"
    )
    chat_id: Optional[str] = Field(
        None, description="Unique identifier for the chat session, if one exists"
    )


class OnboardingChatRequest(BaseModel):
    user_name: str = Field(..., description="User name for onboarding")


class WorkoutJournalChatRequest(BaseModel):
    workout_date: datetime = Field(
        ..., description="Date of the workout being journaled"
    )


class WorkoutGuideChatRequest(BaseModel):
    workout_date: datetime = Field(
        ..., description="Date of the workout guide being asked."
    )


class ChatRequest(BaseChatRequest):
    purpose_data: Optional[
        Union[OnboardingChatRequest, WorkoutJournalChatRequest, WorkoutGuideChatRequest]
    ] = Field(None, description="Purpose-specific data")


class ChatResponse(BaseModel):
    message: str
    chat_id: str
    question: Optional[Dict] = None
    complete: bool


@router.post("/chat", response_class=StreamingResponse)
async def chat(
    request: ChatRequest, current_user: dict = Depends(user_or_admin_required)
):
    """
    Process a chat message and return a response.
    """
    try:
        chat_id = request.chat_id or str(uuid.uuid4())
        user_id = await get_user_id_internal(current_user["email"])
        chat_history = _get_chat_history(chat_id)
        user_message = {"role": "user", "content": request.message}

        client = OpenAI()
        if request.purpose == ChatPurpose.ONBOARDING:
            assistant = OnboardingAssistant(client)
            purpose_data: OnboardingPurposeData = {
                "user_name": request.purpose_data.user_name
            }
        elif request.purpose == ChatPurpose.WORKOUT_JOURNAL:
            assistant = WorkoutJournalAssistant(client)
            purpose_data: WorkoutJournalPurposeData = {
                "workout_date": request.purpose_data.workout_date,
                "user_email": current_user["email"],
            }
        elif request.purpose == ChatPurpose.WORKOUT_GUIDE:
            assistant = WorkoutGuideAssistant(client)
            purpose_data: WorkoutGuidePurposeData = {
                "workout_date": request.purpose_data.workout_date,
                "user_email": current_user["email"],
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid chat purpose")

        ai_response_stream = await assistant.chat(
            chat_history, request.message, purpose_data
        )

        def generate():
            full_response = None
            for extraction in ai_response_stream:
                full_response = extraction
                chat_response = ChatResponse(
                    message=extraction.response if extraction.response else "",
                    chat_id=chat_id,
                    question=(
                        extraction.question.model_dump()
                        if extraction.question
                        else None
                    ),
                    complete=extraction.complete if extraction.complete else False,
                )
                yield f"{json.dumps(chat_response.model_dump())}\n"

            if full_response:
                ai_message = {"role": "assistant", "content": full_response.response}
                chat_history.extend([user_message, ai_message])
                _save_chat_messages(user_id, chat_id, chat_history)

        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as e:
        error_location = traceback.extract_tb(e.__traceback__)[-1]
        error_file = error_location.filename
        error_line = error_location.lineno
        error_message = f"Error in {error_file} at line {error_line}: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/{chat_id}", response_model=List[Dict[str, str]])
async def get_chat_history(chat_id: str):
    """
    Retrieve chat history for a given chat ID.
    """
    try:
        chat_history = _get_chat_history(chat_id)
        return chat_history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/getTodayChatHistory", response_model=List[str])
async def get_today_chat_history(current_user: dict = Depends(user_or_admin_required)):
    """
    Returns a list of chat ids for given user from today, sorted by time (most recent first)
    """
    user_id = await get_user_id_internal(current_user["email"])
    today = datetime.now().date()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    return _get_chat_ids_from_date_range(user_id, today_start, today_end)

@router.get("/getChatHistoryByRange")
async def get_chat_history_by_date_range(
    start_date: str,
    end_date: str,
    current_user: dict = Depends(user_or_admin_required)
):
    """
    Returns a list of chat ids for the given user within the specified date range,
    sorted by time (most recent first)
    """
    user_id = await get_user_id_internal(current_user["email"])

    try:
        start_datetime = datetime.fromisoformat(start_date)
        end_datetime = datetime.fromisoformat(end_date)
    except ValueError:
        error_message = "Invalid date format. Use ISO format (YYYY-MM-DD)."
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=error_message)

    start_datetime = datetime.combine(start_datetime.date(), time.min)
    end_datetime = datetime.combine(end_datetime.date(), time.max)
    return _get_chat_ids_from_date_range(user_id, start_datetime, end_datetime)


def _save_chat_messages(user_id: str, chat_id: str, messages: List[Dict[str, str]]):
    """
    Save chat messages to the database.
    """
    db_operations = DbOperations("chat-history")
    db_operations.collection.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "user_id": user_id,
                "time": datetime.now().isoformat(),
                "messages": messages
            }
        },
        upsert=True
    )

def _get_chat_ids_from_date_range(user_id: str, start_time: datetime, end_time: datetime) -> List[str]:
    """
    Retrieve a list of chat_ids based on start date and end date from chat-history collection.
    """
    db_operations = DbOperations("chat-history")
    try: 
        chats = db_operations.collection.find(
            {
                "user_id": user_id,
                "time": {"$gte": start_time.isoformat(), "$lte": end_time.isoformat()}
            },
            {"chat_id": 1, "time": 1}
        ).sort("time", -1) 
        chat_ids = [chat["chat_id"] for chat in chats]
        return chat_ids
    except Exception as e:
        error_message = f"Error retrieving chat history for user_id: {user_id} with error: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)


def _get_chat_history(chat_id: str) -> list[dict[str, str]]:
    """
    Retrieve chat history from the database.
    Return empty list if chat_id is not found.
    """
    db_operations = DbOperations("chat-history")
    chat_document = db_operations.collection.find_one({"chat_id": chat_id})
    if chat_document and "messages" in chat_document:
        return [
            {"role": m["role"], "content": m["content"]}
            for m in chat_document["messages"]
        ]
    return []
