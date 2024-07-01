from dotenv import load_dotenv
from openai import OpenAI
import os

# Load .env file
load_dotenv()


class GeneratePlan:
    def __init__(self, client: OpenAI):
        self.client = client

    def generate_weekly_plan(self) -> dict:
        system_message = "You are a fitness coach."
        with open("prompts/generate_workout_plan.txt", "r") as file:
            user_message = file.read()
        response = self.client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
        )
        response = response.choices[0].message.content
        print(response)
        return response


if __name__ == "__main__":

    # Create an instance of GeneratePlan
    plan_generator = GeneratePlan(client=OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

    # Generate weekly plan
    weekly_plan = plan_generator.generate_weekly_plan()
