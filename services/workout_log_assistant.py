from openai import OpenAI
from pydantic import BaseModel
from typing import Optional, Dict, Any
from .openai_chat_base import OpenAIBase
from fastapi.responses import StreamingResponse
from .base_assistant import BaseAssistant
import json
from datetime import datetime
from routers.user_profile import get_user_id_internal


class QuestionModel(BaseModel):
    type: str
    options: list[str]  # Can be none, but had to remove Optional due to instructor
    min: Optional[int] = None
    max: Optional[int] = None
    unit: Optional[str] = None


class ResponseModel(BaseModel):
    response: str = None
    question: Optional[QuestionModel] = None
    complete: bool = None


prompt_map = {
    "workout_log_chat": "services/prompts/workout_log_chat.txt",
}


class WorkoutLogAssistant(BaseAssistant):
    def __init__(self, client: OpenAI):
        self.client = OpenAIBase(client)

    async def chat(
        self,
        chat_history: list[dict],
        user_message: str,
        purpose_data: Optional[Dict[str, Any]] = None,
        user_memories: Optional[str] = None,
    ) -> tuple[StreamingResponse, Optional[str]]:
        """
        Process a chat message for the workout guide assistant.

        Args:
            chat_history (list[dict]): The chat history.
            user_message (str): The current user message.
            purpose_data (WorkoutLogPurposeData): Additional data for logging the workout.
                workout_date (datetime): The date of the workout log.
                user_email (str): The email of the user.

        Returns:
            tuple[StreamingResponse, Optional[str]]: The AI's response as a stream and the system message if it's a new conversation.
        """
        system_message = None
        is_new_conversation = not chat_history

        if is_new_conversation:
            with open(prompt_map["workout_log_chat"], "r") as file:
                system_message = file.read()
                if user_memories:
                    system_message = system_message.replace(
                        "{instructions}", user_memories
                    )
        elif chat_history[0]["role"] == "system":
            system_message = chat_history[0]["content"]
            chat_history = chat_history[1:]
        response_data = self.client.chat_json_output_stream(
            chat_history, system_message, user_message, ResponseModel
        )

        return response_data, system_message if is_new_conversation else None
