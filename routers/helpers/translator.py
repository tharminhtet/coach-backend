from dotenv import load_dotenv
from openai import OpenAI
from fastapi import HTTPException, UploadFile
import os
import logging
import traceback
import tempfile
import contextlib

# Load .env file
load_dotenv()

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 25

class Translator:
    def __init__(self, audio: UploadFile):
        self.audio = audio
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.allowed_types = {'mp3', 'mp4', 'wav', 'mpeg', 'mpga', 'm4a', 'webm'}
        self.max_size_mb = MAX_FILE_SIZE_MB
        self.file_extension = self.audio.filename.split('.')[-1].lower()
        self._validate_audio()

    def _validate_audio(self):
        """
        Check if file is valid type and file size is less than 25 MB.
        """
        # Check file type
        if self.file_extension not in self.allowed_types:
            error_message = f"Unsupported file type. Allowed types are: {', '.join(self.allowed_types)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=400, detail=error_message)

        # Check file size
        file_size_mb = self.audio.file.seek(0, os.SEEK_END) / (1024 * 1024)
        self.audio.file.seek(0)  # Reset file pointer
        if file_size_mb <= 0:
            error_message = "The uploaded file is empty"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=400, detail=error_message)
        elif file_size_mb > self.max_size_mb:
            error_message = f"File size exceeds the maximum limit of {self.max_size_mb} MB"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=400, detail=error_message)

    def translate(self):
        """
        Translate given audio to text and post processing with AI for misspell.
        """
        temp_file_path = None
        try:
            file_content = self.audio.file.read()
            # Convert to a temporary file for OpenAI 
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{self.file_extension}') as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
                
            with open(temp_file_path, 'rb') as audio_file:
                translation = self.client.audio.translations.create(
                    model="whisper-1",
                    file=audio_file,
                )
            # Post-processing for any mis-spelling.
            corrected_text = self._post_process(translation.text)
            return corrected_text
        except Exception as e:
            error_message = f"Translation failed: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)
        finally:
            # Ensure the file is deleted even if an exception occurs
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp_file_path)

    def transcribe(self):
        """
        Transcribe given audio to text and post process with AI for misspellings.
        """
        temp_file_path = None
        try:
            file_content = self.audio.file.read()
            # Convert to a temporary file for OpenAI 
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{self.file_extension}') as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
                
            with open(temp_file_path, 'rb') as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            # Post-processing for any mis-spelling.
            corrected_text = self._post_process(transcription.text)
            return corrected_text
        except Exception as e:
            error_message = f"Transcription failed: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=error_message)
        finally:
            # Ensure the file is deleted even if an exception occurs
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp_file_path)

    def _post_process(self, text):
        """
        Correct given text for any misspell or grammatical mistake and remove unnecessary characters.
        """
        with open('routers/helpers/prompts/correct_translation_system_message.txt', 'r') as file:
            system_message = file.read().strip()
            system_message = system_message.replace("{translated_text}", text)
        user_message = f"Please correct any spelling errors in the given text."
        
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ]
        )
        
        return response.choices[0].message.content.strip()