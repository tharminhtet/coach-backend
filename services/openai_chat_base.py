from openai import OpenAI
import json
import instructor
from pydantic import BaseModel
from rich.console import Console
from typing import Type, Optional


class OpenAIBase:
    def __init__(self, client: OpenAI):
        self.client = client
        self.instructor_client = instructor.from_openai(client)
        self.model = "gpt-4o"

    def chat_json_output_stream(
        self,
        chat_history: list[dict],
        system_message: str,
        user_message: str,
        response_model: Type[BaseModel],
    ):
        response_stream = self.instructor_client.chat.completions.create_partial(
            model=self.model,
            response_model=response_model,
            messages=[
                {"role": "system", "content": system_message},
            ]
            + chat_history
            + [{"role": "user", "content": user_message}],
            stream=True,
        )
        return response_stream

    def chat_json_output(
        self, chat_history: list[dict], system_message: str, user_message: str
    ) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
            ]
            + chat_history
            + [{"role": "user", "content": user_message}],
        )
        return json.loads(response.choices[0].message.content)

    def chat_str_output(
        self, chat_history: list[dict], system_message: str, user_message: str
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_message},
            ]
            + chat_history
            + [{"role": "user", "content": user_message}],
        )

        return response.choices[0].message.content
