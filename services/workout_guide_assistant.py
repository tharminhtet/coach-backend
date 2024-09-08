from openai import OpenAI
from pydantic import BaseModel
from typing import TypedDict, Optional
from .openai_chat_base import OpenAIBase
from fastapi.responses import StreamingResponse
from .base_assistant import BaseAssistant
import json
from datetime import datetime
from routers.helpers.generate_plan_helpers import _get_weekly_training_plan_internal
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


class WorkoutGuidePurposeData(TypedDict):
    workout_date: datetime
    user_email: str


prompt_map = {
    "workout_guide_checkin_chat": "services/prompts/workout_guide_chat.txt",
}


class WorkoutGuideAssistant(BaseAssistant):
    def __init__(self, client: OpenAI):
        self.client = OpenAIBase(client)

    async def chat(
        self,
        chat_history: list[dict],
        user_message: str,
        purpose_data: WorkoutGuidePurposeData,
    ) -> tuple[StreamingResponse, Optional[str]]:
        """
        Process a chat message for the workout guide assistant.

        Args:
            chat_history (list[dict]): The chat history.
            user_message (str): The current user message.
            purpose_data (WorkoutGuidePurposeData): Additional data for the workout guide.
                workout_date (datetime): The date of the workout.
                user_email (str): The email of the user.

        Returns:
            tuple[StreamingResponse, Optional[str]]: The AI's response as a stream and the system message if it's a new conversation.
        """
        system_message = None
        is_new_conversation = not chat_history

        if is_new_conversation:
            with open(prompt_map["workout_guide_checkin_chat"], "r") as file:
                system_message = file.read()
        elif chat_history[0]["role"] == "system":
            system_message = chat_history[0]["content"]
            chat_history = chat_history[1:]


        workout_journal_data = await self._retrieve_workout_journal_data(
            purpose_data["workout_date"], purpose_data["user_email"]
        )
        system_message = system_message.replace(
            "{%weekly_workout_plan%}",
            json.dumps(workout_journal_data),
        )

        response_data = self.client.chat_json_output_stream(
            chat_history, system_message, user_message, ResponseModel
        )

        return response_data, system_message if is_new_conversation else None

    async def _retrieve_workout_journal_data(
        self, workout_date: datetime, user_email: str
    ) -> dict:
        user_id = await get_user_id_internal(user_email)
        return await _get_weekly_training_plan_internal(workout_date, user_id)
