import logging
import os
import tempfile
from typing import Optional

from telegram import Update, Voice
from telegram.ext import ContextTypes
from google.cloud import speech
from google.oauth2 import service_account

from config.config import settings

logger = logging.getLogger(__name__)

async def download_voice_message(voice_file_id: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Downloads a voice message from Telegram and saves it to a temporary file."""
    try:
        bot = context.bot
        voice_file = await bot.get_file(voice_file_id)
        
        # Create a temporary file to save the downloaded voice message
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio_file:
            await voice_file.download_to_drive(custom_path=temp_audio_file.name)
            logger.info(f"Voice message downloaded to temporary file: {temp_audio_file.name}")
            return temp_audio_file.name
    except Exception as e:
        logger.error(f"Error downloading voice message {voice_file_id}: {e}", exc_info=True)
        return None

def transcribe_english_voice(audio_file_path: str) -> Optional[str]:
    """Transcribes an English voice message using Google Cloud Speech-to-Text."""
    if not settings.GOOGLE_APPLICATION_CREDENTIALS:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set. Voice transcription requires Google Cloud credentials.")
        return None
    if not os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
        logger.warning(f"Google credentials file not found at: {settings.GOOGLE_APPLICATION_CREDENTIALS}. Voice transcription disabled.")
        return None

    try:
        # Load credentials explicitly from the file
        credentials = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS
        )
        
        client_options = {"api_endpoint": "eu-speech.googleapis.com"} if settings.GEMINI_LOCATION == "europe-west1" else {}
        client = speech.SpeechClient(credentials=credentials, client_options=client_options)

        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        
        # Updated configuration based on stt.py working implementation
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS, # Changed from OGG_OPUS to WEBM_OPUS
            sample_rate_hertz=48000,  # Changed from 16000 to 48000 Hz for Telegram voice messages
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="default", # Added model specification
        )

        logger.info(f"Sending audio file {audio_file_path} for transcription to Google STT with WEBM_OPUS encoding and 48000Hz sample rate.")
        response = client.recognize(config=config, audio=audio)

        if not response.results or not response.results[0].alternatives:
            logger.warning(f"No transcription result for {audio_file_path}")
            # Add more detailed error info
            if hasattr(response, 'error') and response.error and response.error.message:
                logger.warning(f"API Error: {response.error.message}")
            elif not response.results:
                logger.warning("Response contained no results.")
            
            # If WEBM_OPUS fails, try with OGG_OPUS as fallback
            logger.info(f"Retrying with OGG_OPUS encoding for {audio_file_path}")
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                sample_rate_hertz=48000,
                language_code="en-US",
                enable_automatic_punctuation=True,
                model="default",
            )
            response = client.recognize(config=config, audio=audio)
            
            if not response.results or not response.results[0].alternatives:
                logger.warning(f"No transcription result with OGG_OPUS fallback for {audio_file_path}")
                return None
        
        transcription = response.results[0].alternatives[0].transcript
        logger.info(f"Transcription successful for {audio_file_path}: '{transcription}'")
        return transcription

    except Exception as e:
        logger.error(f"Error during Google STT transcription for {audio_file_path}: {e}", exc_info=True)
        return None
    finally:
        # Clean up the temporary audio file
        if os.path.exists(audio_file_path):
            try:
                os.remove(audio_file_path)
                logger.debug(f"Temporary audio file {audio_file_path} deleted.")
            except OSError as e_os:
                logger.error(f"Error deleting temporary audio file {audio_file_path}: {e_os}")

async def process_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Downloads and transcribes a voice message."""
    if not update.message or not update.message.voice:
        return None

    voice: Voice = update.message.voice
    logger.info(f"Received voice message. File ID: {voice.file_id}, Duration: {voice.duration}s, MIME: {voice.mime_type}")

    # Basic validation (e.g., duration, file size if available)
    if voice.duration > 300: # Example: limit to 5 minutes
        await update.message.reply_text("Your voice file is too long. Please send shorter files.")
        logger.warning(f"Voice message too long: {voice.duration}s. User: {update.effective_user.id}")
        return None
    
    temp_audio_path = await download_voice_message(voice.file_id, context)
    if not temp_audio_path:
        await update.message.reply_text("Sorry, there was a problem downloading your voice file.")
        return None

    transcribed_text = transcribe_english_voice(temp_audio_path)

    if not transcribed_text:
        await update.message.reply_text("Sorry, I could not recognize your voice. Please try again or type your message.")
        return None
    
    return transcribed_text 