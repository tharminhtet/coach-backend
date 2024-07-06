from openai import OpenAI
import json


class OpenAIBase:
    def __init__(self, client: OpenAI):
        self.client = client
        self.model = "gpt-4o"

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
