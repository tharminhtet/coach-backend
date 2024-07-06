from openai import OpenAI
from pydantic import BaseModel
from typing import Optional
from .openai_base import OpenAIBase


class QuestionModel(BaseModel):
    type: str
    options: Optional[list[str]] = None
    min: Optional[int] = None
    max: Optional[int] = None
    unit: Optional[str] = None


class ResponseModel(BaseModel):
    response: str
    question: Optional[QuestionModel] = None
    complete: bool


prompt_map = {
    "onboarding_assessment": "services/prompts/onboarding_assessment.txt",
    "summarize_onboarding_assessment": "services/prompts/summarize_onboarding_assessment.txt",
}


class OnboardingAssistant:
    def __init__(self, client: OpenAI):
        self.client = OpenAIBase(client)

    def chat(self, chat_history: list[dict], user_message: str) -> ResponseModel:
        with open(prompt_map["onboarding_assessment"], "r") as file:
            system_message = file.read()
        response_data = self.client.chat_json_output(
            chat_history, system_message, user_message
        )
        return ResponseModel(**response_data)

    def summarize(self, chat_history: list[dict]) -> str:
        with open(prompt_map["summarize_onboarding_assessment"], "r") as file:
            system_message = file.read()
        return self.client.chat_str_output(
            chat_history,
            system_message,
            "Summarize the content as instructed.",
        )
