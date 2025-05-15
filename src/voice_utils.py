import logging
import os
import tempfile
from typing import Optional

from telegram import Update, Voice
from telegram.ext import ContextTypes
from google.cloud import speech

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

def transcribe_persian_voice(audio_file_path: str) -> Optional[str]:
    """Transcribes a Persian voice message using Google Cloud Speech-to-Text."""
    if not settings.GOOGLE_APPLICATION_CREDENTIALS:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set. Skipping transcription.")
        return None
    if not os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
        logger.warning(f"Google credentials file not found at: {settings.GOOGLE_APPLICATION_CREDENTIALS}. Skipping transcription.")
        return None

    try:
        client_options = {"api_endpoint": "eu-speech.googleapis.com"} if settings.GEMINI_LOCATION == "europe-west1" else {}
        client = speech.SpeechClient(client_options=client_options) # Consider client_options for regional endpoints

        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        # Note: Ensure your audio is in a compatible format (e.g., OGG Opus for Telegram voice)
        # If not, ffmpeg might be needed for conversion.
        # Telegram voice messages are typically Opus encoded in an OGG container.
        # The API should handle OGG Opus if specified correctly or if auto-detection works.
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS, # More specific for Telegram
            sample_rate_hertz=16000,  # Telegram voice messages are often 16kHz
            language_code="fa-IR",
            enable_automatic_punctuation=True,
            # model="telephony" or "medical_dictation" if applicable
        )

        logger.info(f"Sending audio file {audio_file_path} for transcription to Google STT.")
        response = client.recognize(config=config, audio=audio)

        if not response.results or not response.results[0].alternatives:
            logger.warning(f"No transcription result for {audio_file_path}")
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
        await update.message.reply_text("فایل صوتی شما بیش از حد طولانی است. لطفاً فایل‌های کوتاه‌تر ارسال کنید.")
        logger.warning(f"Voice message too long: {voice.duration}s. User: {update.effective_user.id}")
        return None
    
    temp_audio_path = await download_voice_message(voice.file_id, context)
    if not temp_audio_path:
        await update.message.reply_text("متاسفانه در دانلود فایل صوتی مشکلی پیش آمد.")
        return None

    transcribed_text = transcribe_persian_voice(temp_audio_path)

    if not transcribed_text:
        await update.message.reply_text("متاسفانه در تبدیل گفتار به نوشتار مشکلی پیش آمد. لطفاً دوباره تلاش کنید یا پیام خود را بنویسید.")
        return None
    
    return transcribed_text 