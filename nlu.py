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

    current_jalali_year = get_current_jalali_year()
    context_instruction = ""
    
    # Handle specific contexts
    if current_context == "voice_transcription":
        context_instruction = "This is a transcribed voice message. Assume the user is trying to set a reminder. Extract the task and any date/time information carefully."
    elif current_context == "initial_contact":
        context_instruction = "This is the start of a new conversation. The user is likely setting a reminder, asking for help, or listing reminders."
    elif current_context:
        context_instruction = f"Current conversation context/state: '{current_context}'."
    else:
        context_instruction = "No specific prior conversation context (this is a new interaction or the start of a reminder sequence)."

    prompt = f"""
    You are an intelligent assistant for a Telegram Reminder Bot, primarily for Persian users, but you should also understand similar English requests.
    Your goal is to analyze user input and extract structured information for reminders, considering any provided conversation context.
    {context_instruction}

    Output MUST be a single JSON object. Do NOT include any text before or after the JSON object (e.g. no "```json" or "```" wrappers).

    JSON Output Structure:
    - "intent": string - REQUIRED. One of ["set_reminder", "provide_task", "provide_date", "provide_time", "provide_am_pm", "list_reminders", "delete_reminder_by_number", "affirmative", "negative", "cancel", "other"].
    - "task": string | null - The reminder's subject. If context is 'awaiting_task_description', this field should contain the extracted task.
    - "date": string | null - Date string. Prioritize Persian relative (e.g., "فردا", "پس‌فردا", "امروز", "شنبه آینده"). Jalali format "YYYY/MM/DD". For English dates (e.g., "tomorrow", "July 20th"), convert to Persian relative or a standard "YYYY-MM-DD" Gregorian.
    - "time": string | null - Time in "HH:MM" (24-hour) format. If context is 'awaiting_am_pm', this field should be null.
    - "recurrence": string | null - Lowercase. e.g., "daily", "weekly", "monthly", "every monday", "every fri".
    - "am_pm": string | null - Relevant if time is ambiguous. "am" (for صبح), "pm" (for ظهر, بعد از ظهر, عصر, شب).
    - "extracted_number": integer | null - For list operations like "delete number 2".
    - "raw_time_input": string | null - The user's raw time input ONLY if AM/PM needs clarification (e.g., if user says "ساعت ۱۲" and you output time as "12:00" but am_pm as null). Otherwise, this should be null.

    Key Guidelines & Contextual Interpretation:
    1.  Intent: Determine the most specific intent. If no other intent fits, use "other".
    2.  Missing Info for "set_reminder": If user intends to set a reminder but parts are missing, still use "set_reminder" intent and return null for missing "task", "date", or "time".
    3.  Date Processing:
        - Persian text dates ("۲۰ اردیبهشت {current_jalali_year}") convert to "YYYY/MM/DD" Jalali (e.g., "{current_jalali_year}/02/20").
        - If year is omitted for Persian textual month dates (e.g., "۲۰ اردیبهشت"), assume current Jalali year: {current_jalali_year}.
        - Persian months: فروردین (01), اردیبهشت (02), خرداد (03), تیر (04), مرداد (05), شهریور (06), مهر (07), آبان (08), آذر (09), دی (10), بهمن (11), اسفند (12).
    4.  Time Processing:
        - Normalize to HH:MM (24h). "۱۰ صبح" -> "10:00" (am_pm: "am"). "۵ و نیم بعد از ظهر" -> "17:30" (am_pm: "pm").
        - Vague times: "صبح زود" -> "07:00", "ظهر" -> "12:00", "بعد از ظهر"/"عصر" -> "17:00", "شب" -> "21:00". Infer am_pm.
        - If only a day is given for a "set_reminder" intent (e.g., "فردا یادم بنداز X"), "time" should be null. The bot will apply a default 09:00 AM.
        - Ambiguous Time: If user says "ساعت ۱۲" (or "12 o'clock") and context is 'awaiting_time_only' or 'awaiting_full_datetime':
            Set "time": "12:00", "am_pm": null, "raw_time_input": "ساعت ۱۲" (or original English). Bot will then ask for AM/PM.
    5.  Contextual Replies:
        - If context is 'awaiting_task_description', user's text is the task: "intent": "provide_task", "task": "[user's text]".
        - If context is 'awaiting_full_datetime', user's text is date/time: "intent": "provide_date" (or "provide_time" or "set_reminder" if full), extract "date", "time", "am_pm".
        - If context is 'awaiting_time_only', user's text is time: "intent": "provide_time", extract "time", "am_pm", "raw_time_input" if ambiguous.
        - If context is 'awaiting_am_pm_clarification' (e.g., bot asked "12 AM or PM?"), user says "ظهر" or "PM": "intent": "provide_am_pm", "am_pm": "pm".
    6.  Recurrence: "هر روز", "روزانه" -> "daily". "هر هفته", "هفتگی" -> "weekly". "هر ماه", "ماهانه" -> "monthly". "هر دوشنبه ساعت ۷" -> "every monday", time: "07:00".
    7.  List/Delete: "یادآور‌هامو نشونم بده" -> "intent": "list_reminders". "حذف کن شماره ۲" -> "intent": "delete_reminder_by_number", "extracted_number": 2.
    8.  Affirmative/Negative/Cancel: "آره", "بله" -> "affirmative". "نه", "خیر" -> "negative". "لغو", "کنسل" -> "cancel".
    9.  Voice Transcription Special Handling: For transcribed voice messages, be more lenient and try to extract as much information as possible. For phrases like "بلافاصله {task}" or "زود {task}", set "date" to "امروز" (today) and "time" to the next available hour or 1 hour from now.

    Examples:
    - User: "فردا ساعت ۱۰ صبح یادم بنداز شیر بخرم" (Context: None) -> {{"intent": "set_reminder", "task": "شیر بخرم", "date": "فردا", "time": "10:00", "recurrence": null, "am_pm": "am", "extracted_number": null, "raw_time_input": null}}
    - User: "یادم بنداز به خواهرم زنگ بزنم" (Context: None) -> {{"intent": "set_reminder", "task": "به خواهرم زنگ بزنم", "date": null, "time": null, "recurrence": null, "am_pm": null, "extracted_number": null, "raw_time_input": null}}
    - User: "فردا" (Context: 'awaiting_full_datetime' for task 'به خواهرم زنگ بزنم') -> {{"intent": "provide_date", "task": null, "date": "فردا", "time": null, "recurrence": null, "am_pm": null, "extracted_number": null, "raw_time_input": null}}
    - User: "ساعت ۱۲" (Context: 'awaiting_time_only' for reminder 'X' on 'Y' day, previously set for 09:00) -> {{"intent": "provide_time", "task": null, "date": null, "time": "12:00", "recurrence": null, "am_pm": null, "extracted_number": null, "raw_time_input": "ساعت ۱۲"}}
    - User: "ظهر" (Context: 'awaiting_am_pm_clarification' for time '12:00') -> {{"intent": "provide_am_pm", "task": null, "date": null, "time": null, "recurrence": null, "am_pm": "pm", "extracted_number": null, "raw_time_input": null}}
    - User: "هر روز ساعت ۸ شب یادم بنداز داروهامو بخورم" (Context: None) -> {{"intent": "set_reminder", "task": "داروهامو بخورم", "date": null, "time": "20:00", "recurrence": "daily", "am_pm": "pm", "extracted_number": null, "raw_time_input": null}}
    - User: "یادآور‌هامو نشونم بده" (Context: None) -> {{"intent": "list_reminders", "task": null, "date": null, "time": null, "recurrence": null, "am_pm": null, "extracted_number": null, "raw_time_input": null}}
    - User: "حذف شماره ۳" (Context: 'awaiting_delete_number_confirm' after list shown) -> {{"intent": "delete_reminder_by_number", "task": null, "date": null, "time": null, "recurrence": null, "am_pm": null, "extracted_number": 3, "raw_time_input": null}}
    - User: "لغو" (Context: any) -> {{"intent": "cancel", "task": null, "date": null, "time": null, "recurrence": null, "am_pm": null, "extracted_number": null, "raw_time_input": null}}
    - User: "خرید هفتگی برای خونه هر شنبه ساعت ۱۰ صبح" (Context: None) -> {{"intent": "set_reminder", "task": "خرید هفتگی برای خونه", "date": null, "time": "10:00", "recurrence": "every saturday", "am_pm": "am", "extracted_number": null, "raw_time_input": null}}
    - User: "نه ممنون" (Context: Bot asked if user wants to change time) -> {{"intent": "negative", "task": null, "date": null, "time": null, "recurrence": null, "am_pm": null, "extracted_number": null, "raw_time_input": null}}
    - User: "فردا ساعت ۲ به دوستم زنگ بزنم" (Context: 'voice_transcription') -> {{"intent": "set_reminder", "task": "به دوستم زنگ بزنم", "date": "فردا", "time": "14:00", "recurrence": null, "am_pm": "pm", "extracted_number": null, "raw_time_input": null}}


    User input: "{text}"
    JSON Output:
    """
    try:
        logger.info(f"NLU Sending to Gemini (context: {current_context}): '{text}'")
        generation_config = GenerationConfig(
            response_mime_type="application/json",
            temperature=0.05 # Very low temperature for precise JSON output
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
            logger.error(f"NLU Error: No candidates returned from Gemini. Prompt may have been blocked. Finish Reason: {response.prompt_feedback.block_reason if response.prompt_feedback else 'N/A'}")
            return None
        
        if response.candidates[0].finish_reason not in [1, 'STOP', 'MAX_TOKENS']: # 1 is "STOP" for some versions
             logger.error(f"NLU Error: Gemini generation finished with reason: {response.candidates[0].finish_reason}. Content: {response.candidates[0].content.parts if response.candidates[0].content else 'N/A'}")
             # Check for safety ratings
             if response.candidates[0].safety_ratings:
                 for rating in response.candidates[0].safety_ratings:
                     if rating.probability > 1: # HARM_PROBABILITY_NEGLIGIBLE = 1, HARM_PROBABILITY_LOW = 2 etc.
                         logger.error(f"Safety Rating Blocked: Category {rating.category}, Probability {rating.probability}")
             return None


        json_response_text = response.candidates[0].content.parts[0].text.strip()
        
        # Aggressive cleaning for potential markdown, though prompt requests no wrappers
        if json_response_text.startswith("```json"):
            json_response_text = json_response_text[len("```json"):]
        if json_response_text.endswith("```"):
            json_response_text = json_response_text[:-len("```")]
        json_response_text = json_response_text.strip()

        logger.debug(f"NLU Gemini cleaned JSON text: {json_response_text}")
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
        logger.error(f"NLU Error: decoding JSON from Gemini response: {e}. Response text: '{json_response_text if 'json_response_text' in locals() else 'Response text not available'}'", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"NLU Error: interacting with Gemini API: {e}", exc_info=True)
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