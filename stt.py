from google.cloud import speech
import os
import logging

logger = logging.getLogger(__name__)

def transcribe_voice_persian(audio_file_path: str) -> str | None:
    try:
        client = speech.SpeechClient()

        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        
        # Primary configuration for Telegram voice messages
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,  # Telegram uses OGG_OPUS for .oga files
            sample_rate_hertz=48000,  # Common sample rate for voice messages
            language_code="fa-IR",    # Primary language: Persian
            alternative_language_codes=["en-US"],  # Also recognize English
            model="default",
            enable_automatic_punctuation=True,     # Add punctuation
            use_enhanced=True,                     # Use enhanced model for better accuracy
            audio_channel_count=1,                 # Most Telegram voice messages are mono
        )
        
        logger.info(f"Sending audio ({audio_file_path}) to Google STT API with OGG_OPUS encoding...")
        response = client.recognize(config=config, audio=audio)
        logger.info("Received response from Google STT API.")

        if response.results and response.results[0].alternatives:
            transcript = response.results[0].alternatives[0].transcript
            confidence = response.results[0].alternatives[0].confidence
            logger.info(f"STT Transcript: '{transcript}' (confidence: {confidence:.2f})")
            return transcript
            
        # First fallback - try with WEBM_OPUS encoding
        logger.warning(f"No transcription result with OGG_OPUS. Trying WEBM_OPUS...")
        try:
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                sample_rate_hertz=48000,
                language_code="fa-IR",
                alternative_language_codes=["en-US"],
                model="default",
                enable_automatic_punctuation=True,
                use_enhanced=True,
                audio_channel_count=1,
            )
            response = client.recognize(config=config, audio=audio)
            
            if response.results and response.results[0].alternatives:
                transcript = response.results[0].alternatives[0].transcript
                logger.info(f"STT Transcript (WEBM_OPUS): '{transcript}'")
                return transcript
                
            # Second fallback - try with different sample rate
            logger.warning("WEBM_OPUS also failed. Trying with different sample rate...")
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                sample_rate_hertz=16000,  # Try lower sample rate
                language_code="fa-IR",
                alternative_language_codes=["en-US"],
                model="default",
                enable_automatic_punctuation=True,
            )
            response = client.recognize(config=config, audio=audio)
            
            if response.results and response.results[0].alternatives:
                transcript = response.results[0].alternatives[0].transcript
                logger.info(f"STT Transcript (16kHz): '{transcript}'")
                return transcript
                
            # Third fallback - try with phone call model which might work better for low quality audio
            logger.warning("All encoding attempts failed. Trying phone_call model...")
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                sample_rate_hertz=48000,
                language_code="fa-IR",
                model="phone_call",  # Model for telephone audio
            )
            response = client.recognize(config=config, audio=audio)
            
            if response.results and response.results[0].alternatives:
                transcript = response.results[0].alternatives[0].transcript
                logger.info(f"STT Transcript (phone_call model): '{transcript}'")
                return transcript
                
            logger.warning("All transcription attempts failed.")
            return None
            
        except Exception as fallback_error:
            logger.error(f"Error in fallback transcription: {fallback_error}")
            return None
            
    except Exception as e:
        logger.error(f"Error during Google STT transcription: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    # (Keep or adapt the test block from the previous stt.py version)
    test_file = "test_persian_voice.oga" 
    if os.path.exists(test_file) and \
       os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and \
       os.path.exists(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS","dummy_path")):
        print(f"Attempting to transcribe '{test_file}'")
        transcript = transcribe_voice_persian(test_file)
        if transcript:
            print(f"Final Transcription: {transcript}")
        else:
            print("Transcription failed in test.")
    else:
        print(f"Skipping STT test: '{test_file}' not found or GOOGLE_APPLICATION_CREDENTIALS not set/valid.")