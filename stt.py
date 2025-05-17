from google.cloud import speech
import os
# from config import GOOGLE_APPLICATION_CREDENTIALS # Not strictly needed here if env var is set globally

def transcribe_voice_persian(audio_file_path: str) -> str | None:
    try:
        client = speech.SpeechClient()

        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        
        # Telegram voice notes are typically Opus, often at 48000Hz.
        # They can be in Ogg (.oga) or WebM (.webm) containers.
        # The error indicates the API isn't getting a valid sample rate.
        # Let's explicitly set it.
        config = speech.RecognitionConfig(
            # encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS, # Try this first
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS, # Or try this if OGG_OPUS fails
            sample_rate_hertz=48000,  # Explicitly set for Opus from Telegram
            language_code="fa-IR",
            model="default", # "default" or "latest_long". "phone_call" or "telephony" might also be good for voice.
            # use_enhanced=True, # if you have it enabled and it helps
        )
        
        # Alternative if direct Opus handling is problematic:
        # Convert to LINEAR16 (WAV) first using pydub, then use:
        # config = speech.RecognitionConfig(
        #     encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        #     sample_rate_hertz=16000,  # Or whatever rate you convert to
        #     language_code="fa-IR",
        # )

        print(f"Sending audio ({audio_file_path}) to Google STT API with explicit sample rate 48000Hz and WEBM_OPUS encoding...")
        response = client.recognize(config=config, audio=audio)
        print("Received response from Google STT API.")

        if response.results and response.results[0].alternatives:
            transcript = response.results[0].alternatives[0].transcript
            print(f"STT Transcript: {transcript}")
            return transcript
        else:
            error_message = "No transcription result from STT API."
            if hasattr(response, 'error') and response.error and response.error.message:
                 error_message += f" API Error: {response.error.message}"
            elif not response.results:
                error_message += " Response contained no results."
            print(error_message)
            return None
            
    except Exception as e:
        print(f"Error during Google STT transcription: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    # This test requires a sample Persian .oga or .webm file.
    test_file = "test_persian_voice.oga" # You need to create this file and ensure it's valid Opus
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
        if not (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.path.exists(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS","dummy_path"))):
            print("Google credentials are not properly set up in environment or config.")