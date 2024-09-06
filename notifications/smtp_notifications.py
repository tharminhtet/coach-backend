from dotenv import load_dotenv
from email.mime.text import MIMEText
from fastapi import HTTPException
from email.mime.multipart import MIMEMultipart
import logging
import os
import smtplib
import traceback

# Load .env file
load_dotenv(override=True)

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

class SMTPNotifications:
    def __init__(self, text: str, email: str, html_content: str, subject: str):

        self.email = email
        self.subject = subject
        
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.sender_email = os.getenv("SENDER_EMAIL")
    
        self.message = MIMEMultipart("alternative")
        self.message["Subject"] = "Password Reset Request"
        self.message["From"] = self.sender_email
        self.message["To"] = self.email

        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html_content, "html")

        self.message.attach(part1)
        self.message.attach(part2)

    def send_email(self):

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()  # Can be omitted
                server.starttls()
                server.ehlo()  # Can be omitted
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.sender_email, self.email, self.message.as_string())
            logger.info(f"{self.subject} email sent to {self.email}")
        except Exception as e:
            error_message = f"Failed to send {self.subject} email to {self.email}: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)
