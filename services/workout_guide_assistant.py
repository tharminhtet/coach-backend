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
    ) -> StreamingResponse:
        """
        Process a chat message for the workout guide assistant.

        Args:
            chat_history (list[dict]): The chat history.
            user_message (str): The current user message.
            purpose_data (WorkoutGuidePurposeData): Additional data for the workout guide.
                workout_date (datetime): The date of the workout.
                user_email (str): The email of the user.

        Returns:
            StreamingResponse: The AI's response as a stream.
        """
        with open(prompt_map["workout_guide_checkin_chat"], "r") as file:
            system_message = file.read()

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
        return response_data

    async def _retrieve_workout_journal_data(
        self, workout_date: datetime, user_email: str
    ) -> dict:
        user_id = await get_user_id_internal(user_email)
        return await _get_weekly_training_plan_internal(workout_date, user_id)
