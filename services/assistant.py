from openai import OpenAI


class Assistant:
    def __init__(self, client: OpenAI):
        self.client = client

    def chat(self, chat_history: list[dict], user_message: str) -> dict:
        with open("services/prompts/onboarding_assessment.txt", "r") as file:
            assistant_system_message = file.read()

        response = self.client.chat.completions.create(
            model="gpt-4o",
            # response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": assistant_system_message},
            ]
            + chat_history
            + [{"role": "user", "content": user_message}],
        )
        return response.choices[0].message.content
