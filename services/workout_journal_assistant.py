from openai import OpenAI
from pydantic import BaseModel
from typing import TypedDict, List, Dict, Any, Optional
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


class WorkoutJournalPurposeData(TypedDict):
    workout_date: datetime
    user_email: str


prompt_map = {
    "workout_journal_checkin_chat": "services/prompts/workout_journal_checkin_chat.txt",
    "workout_journal_checkin_summarize": "services/prompts/workout_journal_checkin_summarize.txt",
}


class WorkoutJournalAssistant(BaseAssistant):
    def __init__(self, client: OpenAI):
        self.client = OpenAIBase(client)

    async def chat(
        self,
        chat_history: list[dict],
        user_message: str,
        purpose_data: WorkoutJournalPurposeData,
    ) -> StreamingResponse:
        """
        Process a chat message for workout journaling.

        Args:
            chat_history (List[Dict[str, str]]): The chat history.
            user_message (str): The current user message.
            purpose_data (WorkoutJournalPurposeData): Additional data for workout journaling.
                workout_date (datetime): The date of the workout.
                user_email (str): The email of the user.

        Returns:
            StreamingResponse: The AI's response as a stream.
        """
        with open(prompt_map["workout_journal_checkin_chat"], "r") as file:
            system_message = file.read()

        workout_journal_data = await self._retrieve_workout_journal_data(
            purpose_data["workout_date"], purpose_data["user_email"]
        )
        system_message = system_message.replace(
            "{%weekly_workout_plan%}",
            json.dumps(workout_journal_data),
        )
        system_message = system_message.replace(
            "{%current_date%}", purpose_data["workout_date"].strftime("%Y-%m-%d")
        )
        response_data = self.client.chat_json_output_stream(
            chat_history, system_message, user_message, ResponseModel
        )
        return response_data

    async def summarize(
        self, date: str, user_email: str, chat_history: list[dict]
    ) -> str:
        """
        Summarize the daily workout and checkin.
        Based on weekly_training_plan and chat_history between user and assistant.
        """
        with open(prompt_map["workout_journal_checkin_summarize"], "r") as file:
            system_message = file.read()

        # Convert date string to datetime object
        date_obj = datetime.strptime(date, "%Y-%m-%d")

        workout_journal_data = await self._retrieve_workout_journal_data(
            date_obj, user_email
        )
        system_message = system_message.replace(
            "{%workout_journal_data%}",
            json.dumps(workout_journal_data),
        )
        system_message = system_message.replace("{%current_date%}", date)
        return self.client.chat_str_output(
            chat_history,
            system_message,
            "Summarize the content as instructed.",
        )

    async def _retrieve_workout_journal_data(
        self, workout_date: datetime, user_email: str
    ) -> dict:
        user_id = await get_user_id_internal(user_email)
        return await _get_weekly_training_plan_internal(workout_date, user_id)
