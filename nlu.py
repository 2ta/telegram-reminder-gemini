import json
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from config import GEMINI_PROJECT_ID, GEMINI_LOCATION, GEMINI_MODEL_NAME, GOOGLE_APPLICATION_CREDENTIALS
import os
import logging
from typing import Dict, Optional, Any, Union
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


def extract_reminder_details_gemini(text: str, current_context: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not gemini_model_vertex:
        logger.error("NLU Error: Gemini model (Vertex AI) not initialized.")
        return None


    current_jalali_year = get_current_jalali_year()
    context_instruction = ""
    
    # Keep context instructions minimal
    if current_context == "voice_transcription":
        context_instruction = "Transcribed voice message."
    elif current_context == "initial_contact":
        context_instruction = "New conversation."
    elif current_context:
        context_instruction = f"Context: '{current_context}'."
    
    # Improved prompt with Persian examples for better extraction
    prompt = f"""
    AI assistant for Persian Telegram Reminder Bot. Extract reminder details from: "{text}".
    Context: {context_instruction}

    Examples:
    - Input: "یادم بنداز به برادرم زنگ بزنم"
      Output: {{"intent": "set_reminder", "task": "زنگ زدن به برادرم", "date": null, "time": null}}
    - Input: "یادم بنداز فردا به مادرم زنگ بزنم"
      Output: {{"intent": "set_reminder", "task": "زنگ زدن به مادرم", "date": "فردا", "time": null}}
    - Input: "یادم بنداز ساعت ۵ به دوستم پیام بدم"
      Output: {{"intent": "set_reminder", "task": "پیام دادن به دوستم", "date": null, "time": "17:00"}}
    - Input: "یادم بنداز هر روز ورزش کنم"
      Output: {{"intent": "set_reminder", "task": "ورزش کردن", "recurrence": "daily"}}

    JSON Output:
    - "intent": string - ["set_reminder", "provide_task", "provide_date", "provide_time", "provide_am_pm", "list_reminders", "delete_reminder_by_number", "request_edit_last_reminder", "request_primary_event_time", "affirmative", "negative", "cancel", "other"].
    - "task": string | null - Reminder subject (e.g., "زنگ زدن به برادرم").
    - "date": string | null - Date. Prefer Persian relative (e.g., "فردا", "پس‌فردا").
    - "time": string | null - Time in "HH:MM" format.
    - "recurrence": string | null - e.g., "daily", "weekly", "monthly".
    - "am_pm": string | null - "am" (صبح) or "pm" (بعد از ظهر).
    - "extracted_number": integer | null - For operations like "delete number 2".
    - "raw_time_input": string | null - Raw time if AM/PM needs clarification.
    - "primary_event_task": string | null - The main event the reminder is relative to.
    - "relative_offset_description": string | null - e.g., "نیم ساعت قبل", "10 minutes after".

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