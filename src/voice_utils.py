import logging
import os
import tempfile
from typing import Optional
import httpx
import json
import base64

from telegram import Update, Voice
from telegram.ext import ContextTypes

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

async def transcribe_voice_with_api_key(audio_file_path: str, language_code: str = "fa-IR") -> Optional[str]:
    """Transcribes a voice message using Google Speech-to-Text API with API key authentication."""
    if not settings.GEMINI_API_KEY:
        logger.warning("GOOGLE_API_KEY not set. Cannot transcribe voice messages.")
        return None

    try:
        # Read the audio file and encode it as base64
        with open(audio_file_path, "rb") as audio_file:
            audio_content = audio_file.read()
            audio_base64 = base64.b64encode(audio_content).decode('utf-8')

        # Prepare the request for Google Speech-to-Text API
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={settings.GEMINI_API_KEY}"
        
        # Configuration for Telegram voice messages (OGG Opus format)
        payload = {
            "config": {
                "encoding": "OGG_OPUS",
                "sampleRateHertz": 48000,  # Telegram voice messages are typically 48kHz
                "languageCode": language_code,  # Persian language
                "enableAutomaticPunctuation": True,
                "model": "default"
            },
            "audio": {
                "content": audio_base64
            }
        }

        logger.info(f"Sending audio file {audio_file_path} for transcription to Google STT API with {language_code} language")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 403:
                error_data = response.json() if response.content else {}
                error_message = error_data.get('error', {}).get('message', 'Permission denied')
                
                if 'SERVICE_DISABLED' in str(error_data) or 'has not been used' in error_message:
                    logger.error("Google Speech-to-Text API is not enabled for this project")
                    logger.error("Please enable it at: https://console.developers.google.com/apis/api/speech.googleapis.com/overview")
                else:
                    logger.error(f"Google STT API permission error: {error_message}")
                return None
                
            elif response.status_code != 200:
                logger.error(f"Google STT API error: {response.status_code} - {response.text}")
                return None
                
            result = response.json()
            
            # Check if we got results
            if not result.get('results') or not result['results'][0].get('alternatives'):
                logger.warning(f"No transcription result for {audio_file_path}")
                
                # Try with English as fallback
                if language_code != "en-US":
                    logger.info(f"Retrying with English for {audio_file_path}")
                    payload["config"]["languageCode"] = "en-US"
                    
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('results') and result['results'][0].get('alternatives'):
                            transcription = result['results'][0]['alternatives'][0]['transcript']
                            logger.info(f"English transcription successful for {audio_file_path}: '{transcription}'")
                            return transcription
                
                return None
            
            transcription = result['results'][0]['alternatives'][0]['transcript']
            confidence = result['results'][0]['alternatives'][0].get('confidence', 0.0)
            logger.info(f"Transcription successful for {audio_file_path}: '{transcription}' (confidence: {confidence:.2f})")
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

def transcribe_english_voice(audio_file_path: str) -> Optional[str]:
    """Legacy function - redirects to new async implementation."""
    logger.warning("Legacy transcribe_english_voice called - this should be replaced with async version")
    return None

async def process_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Downloads and transcribes a voice message."""
    if not update.message or not update.message.voice:
        return None

    voice: Voice = update.message.voice
    logger.info(f"Received voice message. File ID: {voice.file_id}, Duration: {voice.duration}s, MIME: {voice.mime_type}")

    # Basic validation (e.g., duration, file size if available)
    if voice.duration > 300:  # Example: limit to 5 minutes
        await update.message.reply_text("پیام صوتی شما خیلی طولانی است. لطفاً فایل‌های کوتاه‌تر ارسال کنید.")
        logger.warning(f"Voice message too long: {voice.duration}s. User: {update.effective_user.id}")
        return None
    
    temp_audio_path = await download_voice_message(voice.file_id, context)
    if not temp_audio_path:
        await update.message.reply_text("متأسفم، مشکلی در دانلود فایل صوتی شما پیش آمد.")
        return None

    # Try Persian first, then English as fallback
    transcribed_text = await transcribe_voice_with_api_key(temp_audio_path, "fa-IR")
    
    if not transcribed_text:
        # Try English as fallback
        logger.info("Persian transcription failed, trying English...")
        transcribed_text = await transcribe_voice_with_api_key(temp_audio_path, "en-US")

    if not transcribed_text:
        await update.message.reply_text("متأسفم، نتوانستم صدای شما را تشخیص دهم. لطفاً دوباره تلاش کنید یا پیام خود را تایپ کنید.")
        return None
    
    return transcribed_text 