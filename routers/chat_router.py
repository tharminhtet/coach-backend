from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from db_operations import DbOperations
from datetime import datetime
import uuid
from services.assistant import Assistant
from openai import OpenAI

router = APIRouter()


class ChatMessage(BaseModel):
    content: str
    role: str
    timestamp: datetime


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    chat_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a chat message and return a response.
    """
    try:
        chat_id = request.chat_id or str(uuid.uuid4())

        chat_history = _get_chat_history(chat_id)
        user_message = {"role": "user", "content": request.message}

        client = OpenAI()
        assistant = Assistant(client)
        ai_response = assistant.chat(chat_history, request.message)
        ai_message = {"role": "assistant", "content": ai_response}
        chat_history.extend([user_message, ai_message])
        _save_chat_messages(chat_id, chat_history)

        return ChatResponse(message=ai_response, chat_id=chat_id)
    except Exception as e:
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


def _save_chat_messages(chat_id: str, messages: List[Dict[str, str]]):
    """
    Save chat messages to the database.
    """
    db_operations = DbOperations("chat-history")
    db_operations.collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"messages": messages}},
        upsert=True,
    )


def _get_chat_history(chat_id: str) -> List[Dict[str, str]]:
    """
    Retrieve chat history from the database.
    """
    db_operations = DbOperations("chat-history")
    chat_document = db_operations.collection.find_one({"chat_id": chat_id})
    if chat_document and "messages" in chat_document:
        return [
            {"role": m["role"], "content": m["content"]}
            for m in chat_document["messages"]
        ]
    return []
