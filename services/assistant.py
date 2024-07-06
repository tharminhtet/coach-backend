from openai import OpenAI
import json
from pydantic import BaseModel
from typing import Optional, List


class QuestionModel(BaseModel):
    type: str
    options: Optional[List[str]] = None
    min: Optional[int] = None
    max: Optional[int] = None
    unit: Optional[str] = None


class ResponseModel(BaseModel):
    response: str
    question: Optional[QuestionModel] = None


class Assistant:
    def __init__(self, client: OpenAI):
        self.client = client

    def chat(self, chat_history: list[dict], user_message: str) -> ResponseModel:
        with open("services/prompts/onboarding_assessment.txt", "r") as file:
            assistant_system_message = file.read()

        response = self.client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": assistant_system_message},
            ]
            + chat_history
            + [{"role": "user", "content": user_message}],
        )

        response_data = json.loads(response.choices[0].message.content)
        return ResponseModel(**response_data)
