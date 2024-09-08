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
    ) -> tuple[StreamingResponse, Optional[str]]:
        """
        Process a chat message for workout journaling.

        Args:
            chat_history (List[Dict[str, str]]): The chat history.
            user_message (str): The current user message.
            purpose_data (WorkoutJournalPurposeData): Additional data for workout journaling.
                workout_date (datetime): The date of the workout.
                user_email (str): The email of the user.

        Returns:
            tuple[StreamingResponse, Optional[str]]: The AI's response as a stream and the system message if it's a new conversation.
        """

        system_message = None
        is_new_conversation = not chat_history

        if is_new_conversation:
            with open(prompt_map["workout_journal_checkin_chat"], "r") as file:
                system_message = file.read()
            training_plan = await self._retrieve_training_plan(
                purpose_data["workout_date"], purpose_data["user_email"]
            )
            system_message = system_message.replace(
                "{%weekly_workout_plan%}",
                json.dumps(training_plan),
            )
            system_message = system_message.replace(
                "{%current_date%}", purpose_data["workout_date"].strftime("%Y-%m-%d")
            )
        elif chat_history[0]["role"] == "system":
            system_message = chat_history[0]["content"]
            chat_history = chat_history[1:]

        response_data = self.client.chat_json_output_stream(
            chat_history, system_message, user_message, ResponseModel
        )
        return response_data, system_message if is_new_conversation else None

    async def summarize(
        self, date: str, user_email: str, chat_history: list[dict]
    ) -> str:
        """
        Summarize the daily workout and checkin.
        Based on weekly_training_plan and chat_history between user and assistant.
        """
        with open(prompt_map["workout_journal_checkin_summarize"], "r") as file:
            system_message = file.read()

        workout_journal_data = await self._retrieve_workout_journal_data(
            datetime.strptime(date, "%Y-%m-%d"), user_email
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

    async def _retrieve_training_plan(
        self, workout_date: datetime, user_email: str
    ) -> dict:
        user_id = await get_user_id_internal(user_email)
        return await _get_weekly_training_plan_internal(workout_date, user_id)
