from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
import logging

from routers.generate_plan import router as generate_plan_router
from routers.chat_router import router as chat_router
from routers.auth.authentication import router as authentication_router
from routers.user_profile import router as user_profile_router
from routers.modify_workout_plan import router as modify_workout_plan_router

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
app.include_router(modify_workout_plan_router)


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
