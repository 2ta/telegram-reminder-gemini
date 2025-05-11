from google.cloud import speech
import os
import logging

logger = logging.getLogger(__name__)

def transcribe_voice_persian(audio_file_path: str) -> str | None:
    try:
        # Check file size before processing to avoid memory issues
        file_size_mb = os.path.getsize(audio_file_path) / (1024 * 1024)
        if file_size_mb > 10:  # Skip files larger than 10MB to avoid OOM
            logging.warning(f"Audio file too large ({file_size_mb:.2f}MB). Skipping transcription.")
            return None
            
        # Create client outside try block to ensure cleanup
        client = speech.SpeechClient()

        # Read audio file in chunks to reduce memory usage
        content = b''
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(audio_file_path, "rb") as audio_file:
            while chunk := audio_file.read(chunk_size):
                content += chunk
                
        audio = speech.RecognitionAudio(content=content)
        
        # Use minimal configuration for Telegram voice messages
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            sample_rate_hertz=48000,
            language_code="fa-IR",
            alternative_language_codes=["en-US"],
            max_alternatives=1,  # Reduce alternatives to save memory
            profanity_filter=False,
            enable_automatic_punctuation=True
        )

        # Set timeout to avoid hanging
        response = client.recognize(config=config, audio=audio, timeout=15.0)

        # Process results
        if not response.results:
            return None
            
        transcription = ""
        for result in response.results:
            if not result.alternatives:
                continue
            transcription += result.alternatives[0].transcript

        return transcription.strip()

    except Exception as e:
        logging.error(f"Error in speech recognition: {e}")
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