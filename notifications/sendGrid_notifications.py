from dotenv import load_dotenv
from fastapi import HTTPException
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import logging
import traceback

# Load .env file
load_dotenv(override=True)

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

class SendGridNotifications:
    def __init__(self, email: str, html_content: str, subject: str):
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        self.email = email
        self.subject = subject
        self.message = Mail(
            from_email=os.getenv("SENDER_EMAIL"),
            to_emails=email,
            subject=subject,
            html_content=html_content
        )

    def send_email(self):
        try:
            SGClient = SendGridAPIClient(self.sendgrid_api_key)
            response = SGClient.send(self.message)
            logger.info(f"{self.subject} sent to {self.email}. Status code: {response.status_code}")
        except Exception as e:
            error_message = f"Failed to send {self.subject} to {self.email}: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)