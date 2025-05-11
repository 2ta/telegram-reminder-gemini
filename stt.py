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
        
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS, # Common for Telegram .oga files
            sample_rate_hertz=48000,
            language_code="fa-IR",
            model="default", 
        )
        
        logger.info(f"Sending audio ({audio_file_path}) to Google STT API...")
        response = client.recognize(config=config, audio=audio)
        logger.info("Received response from Google STT API.")

        if response.results and response.results[0].alternatives:
            transcript = response.results[0].alternatives[0].transcript
            logger.info(f"STT Transcript: {transcript}")
            return transcript
        else:
            error_message = "No transcription result from STT API."
            # Check for more detailed error from response if available
            # This part depends on the structure of `response` when there are no results.
            # For example, some responses might have a `response.error` field.
            # google.cloud.speech.v1.types.RecognizeResponse doesn't directly have .error
            # errors are usually raised as exceptions by client.recognize() if the call itself fails.
            # If the call succeeds but yields no transcription, `response.results` is empty.
            logger.warning(error_message)
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