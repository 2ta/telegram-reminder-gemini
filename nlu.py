import json
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from config import GEMINI_PROJECT_ID, GEMINI_LOCATION, GEMINI_MODEL_NAME, GOOGLE_APPLICATION_CREDENTIALS
import os
import logging
from utils import get_current_jalali_year, normalize_persian_numerals # Ensure these are correctly imported

logger = logging.getLogger(__name__)

try:
    from google.cloud import aiplatform
    if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS) and GEMINI_PROJECT_ID and GEMINI_LOCATION:
        aiplatform.init(project=GEMINI_PROJECT_ID, location=GEMINI_LOCATION)
        gemini_model_vertex = GenerativeModel(GEMINI_MODEL_NAME)
        logger.info(f"Vertex AI initialized with model: {GEMINI_MODEL_NAME} for NLU.")
    else:
        gemini_model_vertex = None
        logger.warning("NLU WARNING: Vertex AI credentials or project/location info missing. NLU will likely fail.")
except ImportError:
    gemini_model_vertex = None
    logger.warning("NLU WARNING: google-cloud-aiplatform not installed. NLU will fail.")
except Exception as e:
    gemini_model_vertex = None
    logger.warning(f"NLU WARNING: Error initializing Vertex AI: {e}. NLU will fail.", exc_info=True)


def extract_reminder_details_gemini(text: str, current_context: str | None = None) -> dict | None:
    if not gemini_model_vertex:
        logger.error("NLU Error: Gemini model (Vertex AI) not initialized.")
        return None

    # Trim input to reduce memory usage
    if len(text) > 500:
        text = text[:500]
        logger.info(f"Input text truncated to 500 chars to save memory")

    current_jalali_year = get_current_jalali_year()
    context_instruction = ""
    
    # Keep context instructions minimal
    if current_context == "voice_transcription":
        context_instruction = "Transcribed voice message."
    elif current_context == "initial_contact":
        context_instruction = "New conversation."
    elif current_context:
        context_instruction = f"Context: '{current_context}'."
    
    # Simplified prompt to reduce token count and memory usage
    prompt = f"""
    AI assistant for Persian Telegram Reminder Bot. Extract reminder details from: "{text}".
    Context: {context_instruction}

    JSON Output:
    - "intent": string - ["set_reminder", "provide_task", "provide_date", "provide_time", "provide_am_pm", "list_reminders", "delete_reminder_by_number", "request_edit_last_reminder", "affirmative", "negative", "cancel", "other"].
    - "task": string | null - Reminder subject.
    - "date": string | null - Date. Prefer Persian relative (e.g., "فردا", "پس‌فردا").
    - "time": string | null - Time in "HH:MM" format.
    - "recurrence": string | null - e.g., "daily", "weekly", "monthly".
    - "am_pm": string | null - "am" (صبح) or "pm" (بعد از ظهر).
    - "extracted_number": integer | null - For operations like "delete number 2".
    - "raw_time_input": string | null - Raw time if AM/PM needs clarification.

    JSON Output:
    """
    try:
        logger.info(f"NLU Sending to Gemini (context: {current_context})")
        generation_config = GenerationConfig(
            max_output_tokens=150, 
            temperature=0.2,
            top_p=0.8,
            top_k=40,
            # response_mime_type="application/json" # Removed for compatibility
        )
        
        # Ensure gemini_model_vertex is not None before calling
        if not gemini_model_vertex:
             logger.error("NLU model not available for generation.")
             return None

        response = gemini_model_vertex.generate_content(
            [Part.from_text(prompt)],
            generation_config=generation_config
        )

        # Check for safety ratings or blocks
        if not response.candidates:
            logger.error(f"NLU Error: No candidates returned from Gemini.")
            return None
        
        json_response_text = response.candidates[0].content.parts[0].text.strip()
        
        # Clean response
        if json_response_text.startswith("```json"):
            json_response_text = json_response_text[len("```json"):]
        if json_response_text.endswith("```"):
            json_response_text = json_response_text[:-len("```")]
        json_response_text = json_response_text.strip()

        parsed_json = json.loads(json_response_text)

        # Normalize numbers in specific fields if Gemini returns Persian numerals
        if parsed_json.get("date"):
            parsed_json["date"] = normalize_persian_numerals(parsed_json.get("date"))
        if parsed_json.get("time"):
            parsed_json["time"] = normalize_persian_numerals(parsed_json.get("time"))
        if parsed_json.get("raw_time_input"):
             parsed_json["raw_time_input"] = normalize_persian_numerals(parsed_json.get("raw_time_input"))
            
        return parsed_json

    except json.JSONDecodeError as e:
        logger.error(f"NLU Error: decoding JSON from Gemini response: {e}")
        return None
    except Exception as e:
        logger.error(f"NLU Error: interacting with Gemini API: {e}")
        return None

# ... (keep or update the if __name__ == '__main__': test block from the previous nlu.py version) ...
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG) # Set logging level for testing
    if not gemini_model_vertex:
        logger.error("NLU: Gemini model (Vertex AI) not available for testing.")
    else:
        # (Add comprehensive test cases here, similar to the previous nlu.py if __name__ block)
        test_cases = [
            ("Initial: یادم بنداز فردا به مادرم زنگ بزنم", None),
            ("Initial: Remind me to call mom", None),
            ("Contextual Date: فردا", "awaiting_full_datetime"),
            ("Contextual Time: ساعت ۳ بعد از ظهر", "awaiting_time_only"),
            ("Contextual AM/PM: صبح", "awaiting_am_pm_clarification"),
            ("Full reminder: هر جمعه ساعت ۷ صبح یادم بنداز برم خرید", None),
            ("List command: یادآورهای من", None),
            ("Delete command: شماره ۲ رو پاک کن", "awaiting_delete_number_confirm"), # Context here is bot state
            ("Cancel command: لغو", "awaiting_task_description"),
            ("Ambiguous time: ساعت ۱۲ یادم بنداز", None), # Should give raw_time_input
            ("Voice transcription: فردا ساعت ۲ به دوستم زنگ بزنم", "voice_transcription"),
            ("Voice transcription: بلافاصله به دوستم زنگ بزنم", "voice_transcription"),
            ("Voice transcription: زود به دوستم زنگ بزنم", "voice_transcription")
        ]
        for desc, text_input, context_input in test_cases:
            print(f"\n--- NLU Testing ({desc}) ---")
            print(f"Input: '{text_input}', Context: '{context_input}'")
            details = extract_reminder_details_gemini(text_input, current_context=context_input)
            if details:
                print(f"NLU Extracted: {json.dumps(details, ensure_ascii=False, indent=2)}")
            else:
                print("NLU: Failed to extract details.")