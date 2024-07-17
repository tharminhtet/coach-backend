# from datetime import date
# from user import UserProfile

# # Create a realistic user profile object
# user_profile = UserProfile(user_id="12345", name="John Doe", age=30, gender="Male")

# # Add some stats to the user profile
# user_profile.add_stats(
#     date_measured=date(2022, 1, 1),
#     available_equipments=["Treadmill", "Dumbbells"],
#     fitness_stats={"weight": "180 lbs", "height": "5'9\"", "bmi": "26.6"},
#     body_measurements={"chest": "40 inches", "waist": "32 inches", "hips": "38 inches"},
#     goals=[{"goal": "Lose weight", "target": "170 lbs"}],
#     constraints=["No heavy lifting due to back injury"],
# )

# # Add another set of stats
# user_profile.add_stats(
#     date_measured=date(2022, 2, 1),
#     available_equipments=["Treadmill", "Dumbbells", "Kettlebell"],
#     fitness_stats={"weight": "175 lbs", "height": "5'9\"", "bmi": "25.8"},
#     body_measurements={"chest": "39 inches", "waist": "31 inches", "hips": "37 inches"},
#     goals=[{"goal": "Lose weight", "target": "170 lbs"}],
#     constraints=["No heavy lifting due to back injury"],
# )


# # Define a method to pretty print the user profile
# def pretty_print_user_profile(user_profile):
#     print("User Profile:")
#     print(f"User ID: {user_profile.user_id}")
#     print(f"Name: {user_profile.name}")
#     print(f"Age: {user_profile.age}")
#     print(f"Gender: {user_profile.gender}")
#     print("\nStats:")
#     for stat in user_profile.stats:
#         print(f"  Date Measured: {stat.date_measured}")
#         print(f"  Available Equipments: {', '.join(stat.available_equipments)}")
#         print(f"  Fitness Stats:")
#         for key, value in stat.fitness_stats.items():
#             print(f"    {key.capitalize()}: {value}")
#         print(f"  Body Measurements:")
#         for key, value in stat.body_measurements.items():
#             print(f"    {key.capitalize()}: {value}")
#         print(f"  Goals:")
#         for goal in stat.goals:
#             print(f"    Goal: {goal['goal']}, Target: {goal['target']}")
#         print(f"  Constraints: {', '.join(stat.constraints)}")
#         print("\n")


# # Call the pretty print function
# pretty_print_user_profile(user_profile)


from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
import logging

from generate_plan_test import router as generate_plan_router
from routers.chat_router import router as chat_router
from authentication import router as authentication_router
from user_profile import router as user_profile_router

from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# if other ports for frontend will be used, add them here
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allowed origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Register routers
app.include_router(generate_plan_router)
app.include_router(chat_router)
app.include_router(authentication_router)
app.include_router(user_profile_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_location = traceback.extract_tb(exc.__traceback__)[-1]
    error_file = error_location.filename
    error_line = error_location.lineno
    error_message = f"Error in {error_file} at line {error_line}: {str(exc)}"
    logging.error(error_message)
    logging.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": error_message},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
