import google.generativeai as genai
import logging
import json
import asyncio
from typing import Dict, Any
from config.config import settings

logger = logging.getLogger(__name__)

async def get_llm_response(prompt: str, model_name: str = settings.GEMINI_MODEL_NAME) -> str:
    """
    Sends a prompt to the Google Generative AI model and returns the text response.
    Runs the synchronous SDK call in a thread pool executor.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("Gemini API key is not configured. Please set GOOGLE_API_KEY or GEMINI_API_KEY in your .env file.")
        raise ValueError("Gemini API key is not configured.")

    try:
        loop = asyncio.get_running_loop()
        
        def _blocking_call():
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(model_name)
            logger.debug(f"Sending prompt to Gemini model {model_name}: {prompt}")
            return model.generate_content(prompt)

        response = await loop.run_in_executor(None, _blocking_call)
        
        if response.candidates:
            if response.candidates[0].content and response.candidates[0].content.parts:
                full_text_response = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
                logger.debug(f"Received response from Gemini: {full_text_response}")
                return full_text_response
            else:
                logger.warning("Gemini response has no content parts or text.")
                if response.candidates[0].finish_reason:
                     logger.warning(f"Gemini response finish reason: {response.candidates[0].finish_reason.name}")
                     if response.prompt_feedback and response.prompt_feedback.block_reason:
                         logger.error(f"Prompt was blocked. Reason: {response.prompt_feedback.block_reason.name}")
                         raise Exception(f"Prompt blocked by API. Reason: {response.prompt_feedback.block_reason.name}")
                return ""
        else:
            logger.warning("Gemini response has no candidates.")
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.error(f"Prompt was blocked. Reason: {response.prompt_feedback.block_reason.name}")
                raise Exception(f"Prompt blocked by API. Reason: {response.prompt_feedback.block_reason.name}")
            return ""

    except ValueError as ve:
        logger.error(f"ValueError in get_llm_response: {ve}")
        raise
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        if hasattr(e, 'response'):
            logger.error(f"Gemini API error response: {e.response}")
        raise Exception(f"Failed to get response from LLM: {e}")

async def get_llm_json_response(prompt_template: str, input_variables: Dict[str, Any], model_name: str = settings.GEMINI_MODEL_NAME) -> Dict[str, Any]:
    """
    Formats a prompt, sends it to the LLM (async), and expects a JSON string, which it parses into a dictionary.
    """
    formatted_prompt = prompt_template.format(**input_variables)
    
    raw_response = await get_llm_response(prompt=formatted_prompt, model_name=model_name)
    
    try:
        if raw_response.strip().startswith("```json"):
            cleaned_response = raw_response.strip()[7:-3].strip()
        elif raw_response.strip().startswith("```"):
             cleaned_response = raw_response.strip()[3:-3].strip()
        else:
            cleaned_response = raw_response.strip()

        if not cleaned_response: # Handle case where LLM returns empty string after cleaning
            logger.warning(f"LLM returned an empty string after cleaning. Raw response: '{raw_response}'")
            # Depending on strictness, either raise ValueError or return a default dict like {"intent": "unknown"}
            # For now, let's assume an empty response means a problem or unparsable content.
            raise ValueError(f"LLM response was empty after cleaning. Raw response: '{raw_response}'")

        parsed_json = json.loads(cleaned_response)
        logger.debug(f"Successfully parsed JSON response: {parsed_json}")
        return parsed_json
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response from LLM. Error: {e}. Raw response: '{raw_response}'")
        raise ValueError(f"LLM response was not valid JSON: {raw_response}") from e

if __name__ == '__main__':
    async def main_test():
        logging.basicConfig(level=logging.DEBUG)
        logger.info("Testing LLM utils (async)...")

        if not settings.GEMINI_API_KEY:
            print("GEMINI_API_KEY (or GOOGLE_API_KEY) not found. Skipping live test.")
            return

        try:
            from resources.prompts import INTENT_DETECTION_PROMPT_TEMPLATE
            
            test_input_text = "سلام خوبی؟"
            test_input_vars = {"user_input": test_input_text, "user_history": "None"}
            
            print(f"\nTesting intent detection for: '{test_input_text}'")
            json_response = await get_llm_json_response(
                prompt_template=INTENT_DETECTION_PROMPT_TEMPLATE,
                input_variables=test_input_vars
            )
            print(f"LLM JSON Response: {json_response}")
            assert isinstance(json_response, dict)
            assert "intent" in json_response

            test_input_text_reminder = "یادآوری کن فردا ساعت ۱۰ صبح به علی زنگ بزنم"
            # Prepare a mock history for the reminder test
            mock_history = "کاربر: سلام\nدستیار: سلام! چطور می‌توانم کمکتان کنم؟"
            test_input_vars_reminder = {"user_input": test_input_text_reminder, "user_history": mock_history}
            print(f"\nTesting intent detection for: '{test_input_text_reminder}' with history")
            json_response_reminder = await get_llm_json_response(
                prompt_template=INTENT_DETECTION_PROMPT_TEMPLATE,
                input_variables=test_input_vars_reminder
            )
            print(f"LLM JSON Response (Reminder): {json_response_reminder}")
            assert isinstance(json_response_reminder, dict)
            assert json_response_reminder.get("intent") == "CREATE_REMINDER"

            print("\nllm_utils.py async basic test completed successfully!")

        except ImportError:
            print("Could not import INTENT_DETECTION_PROMPT_TEMPLATE from resources.prompts.")
        except Exception as e:
            print(f"An error occurred during llm_utils.py async test: {e}")

    asyncio.run(main_test()) 