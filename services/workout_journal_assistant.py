from openai import OpenAI
from pydantic import BaseModel
from typing import TypedDict, List, Dict, Any, Optional
from .openai_chat_base import OpenAIBase
from fastapi.responses import StreamingResponse
from fastapi.responses import StreamingResponse
from .base_assistant import BaseAssistant


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
    workout_date: str
    exercise_data: List[Dict[str, Any]]


prompt_map = {
    "onboarding_assessment": "services/prompts/onboarding_assessment.txt",
    "summarize_onboarding_assessment": "services/prompts/summarize_onboarding_assessment.txt",
}


class WorkoutJournalAssistant:
    def __init__(self, client: OpenAI):
        self.client = OpenAIBase(client)

    def chat(self, chat_history: list[dict], user_message: str) -> StreamingResponse:
        """
        Process a chat message for workout journaling.

        Args:
            chat_history (List[Dict[str, str]]): The chat history.
            user_message (str): The current user message.
            purpose_data (WorkoutJournalPurposeData): Additional data for workout journaling.
                workout_date (datetime): The date of the workout.
                exercise_data (List[Dict[str, Any]]): List of exercises performed.

        Returns:
            StreamingResponse: The AI's response as a stream.
        """
        with open(prompt_map["onboarding_assessment"], "r") as file:
            system_message = file.read()
        response_data = self.client.chat_json_output_stream(
            chat_history, system_message, user_message, ResponseModel
        )
        return response_data

    def summarize(self, chat_history: list[dict]) -> str:
        with open(prompt_map["summarize_onboarding_assessment"], "r") as file:
            system_message = file.read()
        return self.client.chat_str_output(
            chat_history,
            system_message,
            "Summarize the content as instructed.",
        )
