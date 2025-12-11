"""
Intelligent Reminder Agent Module

This module provides enhanced LLM-powered functions for intelligent reminder creation,
improving context understanding, error handling, and user interaction.
"""

import logging
import json
import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import pytz

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config.config import settings
from src.datetime_utils import parse_english_datetime_to_utc, format_datetime_for_display

logger = logging.getLogger(__name__)


def get_current_english_datetime_for_prompt() -> str:
    """Get current datetime in English format for LLM prompts."""
    try:
        now_utc = datetime.now(pytz.utc)
        return now_utc.strftime("%A, %B %d, %Y at %I:%M %p UTC")
    except Exception as e:
        logger.error(f"Error generating current English datetime for prompt: {e}", exc_info=True)
        return "Current date and time unavailable"


async def intelligent_reminder_intent_detection(
    input_text: str,
    conversation_history: Optional[list] = None,
    user_timezone: str = "UTC"
) -> Dict[str, Any]:
    """
    Intelligently detect reminder creation intent using LLM with full context awareness.
    
    This function uses Gemini to:
    - Understand user intent even with incomplete information
    - Extract task, date, time, and recurrence patterns intelligently
    - Handle natural language variations and edge cases
    - Provide confidence scores and reasoning
    
    Args:
        input_text: User's input text
        conversation_history: Previous conversation messages for context
        user_timezone: User's timezone for date/time interpretation
        
    Returns:
        Dict with:
            - is_reminder_intent: bool
            - task: Optional[str]
            - date_str: Optional[str]
            - time_str: Optional[str]
            - recurrence_rule: Optional[str]
            - confidence: str (high/medium/low)
            - reasoning: str
            - needs_clarification: bool
            - clarification_type: Optional[str] (task/date/time/datetime)
    """
    try:
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set. Cannot use intelligent intent detection.")
            return {
                "is_reminder_intent": False,
                "task": None,
                "date_str": None,
                "time_str": None,
                "recurrence_rule": None,
                "confidence": "low",
                "reasoning": "API key not configured",
                "needs_clarification": False,
                "clarification_type": None
            }
        
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL_NAME,
            temperature=0.0,  # Zero temperature for most consistent parsing
            google_api_key=settings.GEMINI_API_KEY,
            max_tokens=2000  # Increased for better parsing of complex inputs
        )
        
        current_datetime = get_current_english_datetime_for_prompt()
        
        # Build conversation context
        context_messages = []
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 6 messages for context
                if isinstance(msg, dict):
                    speaker = msg.get("speaker", "user")
                    text = msg.get("text", "")
                    if speaker == "user":
                        context_messages.append(f"User: {text}")
                    elif speaker == "bot":
                        context_messages.append(f"Bot: {text}")
        
        context_str = "\n".join(context_messages) if context_messages else "No previous conversation context."
        
        prompt = ChatPromptTemplate.from_template("""
You are an expert AI assistant for a reminder bot. Your task is to intelligently analyze user input and determine if they want to create a reminder.

Current datetime: {current_datetime}
User timezone: {user_timezone}
Conversation context:
{conversation_context}

User input: "{input_text}"

Analyze this input with the following considerations:

1. **Intent Detection - BE EXTREMELY PERMISSIVE**:
   - If input contains ANY of these, it's DEFINITELY a reminder intent:
     * "remind me" / "remind me to" / "remind me about" (explicit)
     * Task/action + date/time (e.g., "call my brother at 12 of December at 10 p.m.")
     * Task/action + "at" + date/time (e.g., "call mom at 3pm tomorrow")
     * Any scheduling language (e.g., "meeting on Friday", "appointment next week")
   - DEFAULT TO REMINDER INTENT if there's ANY doubt - better to ask for clarification than miss a reminder
   - Voice transcriptions may have punctuation/formatting differences - be very tolerant
   - CRITICAL EXAMPLES that MUST be detected:
     * "remind me to call my brother at 12 of December at 10 p.m." → DEFINITELY reminder intent
     * "call my brother at 12 of December at 10 p.m." → DEFINITELY reminder intent (even without "remind me")
     * "remind me to call my brother at 12 of December. at 10 p.m." → DEFINITELY reminder intent (period is punctuation)
     * "meeting tomorrow at 3pm" → DEFINITELY reminder intent

2. **Task Extraction**: Extract the main task/action to be reminded about:
   - Remove date/time references from the task
   - Keep the core action (e.g., "call mom", "call my brother", "take medicine", "team meeting")
   - Preserve the user's original language if not English
   - CRITICAL: When user says "remind me to call my brother at 12 of December", extract task="call my brother" (remove the date/time part)

3. **Date Extraction - HANDLE ALL FORMATS**:
   - CRITICAL: Recognize ALL these date formats (all are valid):
     * "12 of December" / "12th of December" / "the 12th of December"
     * "December 12" / "December 12th" / "Dec 12"
     * "12 December" / "12th December"
     * "12/12" / "12-12" (assume current or next year)
   - Relative: "today", "tomorrow", "next week", "in 3 days"
   - Weekdays: "Monday", "Friday", "next Monday"
   - Special: "weekend", "end of month"
   - CRITICAL: When parsing "at 12 of December", the "at" is just a connector - extract "12 of December" as date_str
   - CRITICAL: When parsing "at [date] at [time]", first "at" introduces date, second "at" introduces time
   - CRITICAL: Handle voice transcription variations - "12 of December" might be transcribed as "12 December" or "December 12"

4. **Time Extraction - HANDLE ALL FORMATS**:
   - CRITICAL: Recognize ALL these time formats (all are valid):
     * "10 p.m." / "10 PM" / "10pm" / "10 p.m" / "10PM" / "10 P.M."
     * "10:00 PM" / "10:00pm" / "22:00" / "10:00 p.m."
     * "10 AM" / "10am" / "10 a.m." / "10:00 AM"
   - Relative: "morning", "afternoon", "evening", "tonight", "noon"
   - CRITICAL: When user says "at 10 p.m.", extract time_str="10 p.m." (preserve format)
   - CRITICAL: Handle voice transcription variations - "10 p.m." might be transcribed as "10pm" or "10 PM" - all are valid
   - CRITICAL: Periods in transcriptions (e.g., "at 12 of December. at 10 p.m.") don't affect extraction - extract date and time separately

5. **Recurrence Detection**: Identify recurring patterns:
   - "every day", "daily" → recurrence_rule="daily"
   - "every week", "weekly" → recurrence_rule="weekly"
   - "every month", "monthly" → recurrence_rule="monthly"
   - "every Monday" → recurrence_rule="weekly" (with context)
   - "every morning" → recurrence_rule="daily", time_str="morning"

6. **Clarification Needs**: Determine if information is missing:
   - Missing task → needs_clarification=true, clarification_type="task"
   - Missing date → needs_clarification=true, clarification_type="date"
   - Missing time → needs_clarification=true, clarification_type="time"
   - Missing both → needs_clarification=true, clarification_type="datetime"

7. **Confidence Assessment**: Rate your confidence:
   - "high": Clear intent, complete information
   - "medium": Clear intent, some ambiguity
   - "low": Unclear intent or incomplete information

CRITICAL RULES - FOLLOW THESE STRICTLY:
1. BE EXTREMELY PERMISSIVE: If there's ANY doubt about intent, set is_reminder_intent=true
2. HANDLE VOICE TRANSCRIPTION ERRORS: Voice messages may have punctuation/formatting differences - be very tolerant
3. DATE FORMATS: All these are valid - "12 of December", "12th of December", "December 12", "12 December", "the 12th of December"
4. TIME FORMATS: All these are valid - "10 p.m.", "10 PM", "10pm", "22:00", "10:00 PM"
5. CONNECTOR WORDS: "at" can connect date or time - parse based on context (first "at" usually = date, second "at" usually = time)
6. PUNCTUATION: Periods, commas in transcriptions don't affect date/time extraction - ignore them
7. COMPLETE REQUESTS: If user provides task + date + time, extract all components and set needs_clarification=false
8. TYPOS: Handle variations intelligently (e.g., "tommorow" = "tomorrow", "december" = "December")
9. DEFAULT TO REMINDER: When uncertain, default to reminder intent - better to ask for clarification than miss a reminder

Respond ONLY with valid JSON in this exact format:
{{
    "is_reminder_intent": boolean,
    "task": "string or null",
    "date_str": "string or null",
    "time_str": "string or null",
    "recurrence_rule": "string or null",
    "confidence": "high|medium|low",
    "reasoning": "brief explanation",
    "needs_clarification": boolean,
    "clarification_type": "task|date|time|datetime|null"
}}

Examples:
- Input: "Remind me to call mom tomorrow at 3pm"
  → {{"is_reminder_intent": true, "task": "call mom", "date_str": "tomorrow", "time_str": "3pm", "confidence": "high"}}

- Input: "remind me to call my brother at 12 of December at 10 p.m."
  → {{"is_reminder_intent": true, "task": "call my brother", "date_str": "12 of December", "time_str": "10 p.m.", "confidence": "high"}}

- Input: "remind me to call my brother at 12th of December at 10 p.m."
  → {{"is_reminder_intent": true, "task": "call my brother", "date_str": "12th of December", "time_str": "10 p.m.", "confidence": "high"}}

- Input: "remind me to call my brother on December 12 at 10 p.m."
  → {{"is_reminder_intent": true, "task": "call my brother", "date_str": "December 12", "time_str": "10 p.m.", "confidence": "high"}}

- Input: "tomorrow 10am"
  → {{"is_reminder_intent": true, "task": null, "date_str": "tomorrow", "time_str": "10am", "needs_clarification": true, "clarification_type": "task"}}

- Input: "every day at 8am"
  → {{"is_reminder_intent": true, "task": null, "date_str": "today", "time_str": "8am", "recurrence_rule": "daily", "needs_clarification": true, "clarification_type": "task"}}

Only respond with valid JSON, no other text.
""")
        
        chain = prompt | llm | StrOutputParser()
        
        result = await chain.ainvoke({
            "current_datetime": current_datetime,
            "user_timezone": user_timezone,
            "conversation_context": context_str,
            "input_text": input_text
        })
        
        # Parse JSON response
        try:
            json_str = result.strip()
            # Remove markdown code blocks if present
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            parsed_result = json.loads(json_str)
            
            logger.info(
                f"Intelligent intent detection: '{input_text}' -> "
                f"intent={parsed_result.get('is_reminder_intent')}, "
                f"task='{parsed_result.get('task')}', "
                f"date='{parsed_result.get('date_str')}', "
                f"time='{parsed_result.get('time_str')}', "
                f"confidence={parsed_result.get('confidence')}, "
                f"reasoning='{parsed_result.get('reasoning', 'N/A')}'"
            )
            
            return parsed_result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {result}, error: {e}")
            # Fallback: try to extract basic information
            return {
                "is_reminder_intent": "remind" in input_text.lower() or "reminder" in input_text.lower(),
                "task": None,
                "date_str": None,
                "time_str": None,
                "recurrence_rule": None,
                "confidence": "low",
                "reasoning": f"JSON parse error: {str(e)}",
                "needs_clarification": True,
                "clarification_type": "datetime"
            }
            
    except Exception as e:
        logger.error(f"Error in intelligent_reminder_intent_detection for '{input_text}': {e}", exc_info=True)
        return {
            "is_reminder_intent": False,
            "task": None,
            "date_str": None,
            "time_str": None,
            "recurrence_rule": None,
            "confidence": "low",
            "reasoning": f"Error: {str(e)}",
            "needs_clarification": False,
            "clarification_type": None
        }


async def intelligent_datetime_parsing(
    date_str: Optional[str],
    time_str: Optional[str],
    user_timezone: str = "UTC",
    context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Intelligently parse datetime with LLM assistance for better understanding.
    
    This function uses LLM to:
    - Understand ambiguous time expressions
    - Handle context-aware date/time resolution
    - Provide better error messages
    - Suggest alternatives when parsing fails
    
    Args:
        date_str: Date string from user input
        time_str: Time string from user input
        user_timezone: User's timezone
        context: Additional context (e.g., previous conversation)
        
    Returns:
        Dict with:
            - parsed_datetime_utc: Optional[datetime]
            - date_str_normalized: Optional[str]
            - time_str_normalized: Optional[str]
            - confidence: str
            - error_message: Optional[str]
            - suggestions: Optional[list]
    """
    try:
        if not settings.GEMINI_API_KEY:
            # Fallback to regular parsing
            parsed_dt = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
            return {
                "parsed_datetime_utc": parsed_dt,
                "date_str_normalized": date_str,
                "time_str_normalized": time_str,
                "confidence": "medium" if parsed_dt else "low",
                "error_message": None if parsed_dt else "Could not parse datetime",
                "suggestions": None
            }
        
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL_NAME,
            temperature=0.1,
            google_api_key=settings.GEMINI_API_KEY,
            max_tokens=500
        )
        
        current_datetime = get_current_english_datetime_for_prompt()
        
        prompt = ChatPromptTemplate.from_template("""
You are an expert datetime parser. Your task is to normalize and validate date/time strings.

Current datetime: {current_datetime}
User timezone: {user_timezone}
Context: {context}

Date string: {date_str}
Time string: {time_str}

Your task:
1. Normalize the date and time strings to clear, unambiguous formats
2. Validate that the combination makes sense
3. If ambiguous, provide the most likely interpretation
4. If invalid, explain why and suggest alternatives

Rules:
- Normalize relative dates: "tomorrow" → "tomorrow" (keep relative)
- Normalize times: "3pm" → "3 PM", "14:00" → "2:00 PM" (if 12-hour preferred)
- Handle typos: "tommorow" → "tomorrow"
- For ambiguous times, prefer the most common interpretation

Respond ONLY with valid JSON:
{{
    "date_str_normalized": "normalized date string or null",
    "time_str_normalized": "normalized time string or null",
    "confidence": "high|medium|low",
    "is_valid": boolean,
    "error_message": "error description or null",
    "suggestions": ["suggestion1", "suggestion2"] or null
}}

Only respond with valid JSON, no other text.
""")
        
        chain = prompt | llm | StrOutputParser()
        
        result = await chain.ainvoke({
            "current_datetime": current_datetime,
            "user_timezone": user_timezone,
            "context": context or "No additional context",
            "date_str": date_str or "null",
            "time_str": time_str or "null"
        })
        
        # Parse JSON response
        try:
            json_str = result.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            parsed_result = json.loads(json_str)
            
            # Use normalized strings for parsing
            normalized_date = parsed_result.get("date_str_normalized") or date_str
            normalized_time = parsed_result.get("time_str_normalized") or time_str
            
            # Parse using the normalized strings
            parsed_dt = parse_english_datetime_to_utc(normalized_date, normalized_time, user_timezone)
            
            return {
                "parsed_datetime_utc": parsed_dt,
                "date_str_normalized": normalized_date,
                "time_str_normalized": normalized_time,
                "confidence": parsed_result.get("confidence", "medium"),
                "error_message": parsed_result.get("error_message"),
                "suggestions": parsed_result.get("suggestions")
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM datetime normalization response: {result}, error: {e}")
            # Fallback to regular parsing
            parsed_dt = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
            return {
                "parsed_datetime_utc": parsed_dt,
                "date_str_normalized": date_str,
                "time_str_normalized": time_str,
                "confidence": "medium" if parsed_dt else "low",
                "error_message": None if parsed_dt else "Could not parse datetime",
                "suggestions": None
            }
            
    except Exception as e:
        logger.error(f"Error in intelligent_datetime_parsing: {e}", exc_info=True)
        # Fallback to regular parsing
        parsed_dt = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
        return {
            "parsed_datetime_utc": parsed_dt,
            "date_str_normalized": date_str,
            "time_str_normalized": time_str,
            "confidence": "low",
            "error_message": f"Error: {str(e)}",
            "suggestions": None
        }


async def intelligent_clarification_generation(
    missing_info_type: str,
    collected_task: Optional[str] = None,
    collected_date: Optional[str] = None,
    collected_time: Optional[str] = None,
    user_timezone: str = "UTC"
) -> Dict[str, Any]:
    """
    Generate intelligent clarification questions using LLM.
    
    This function creates context-aware, helpful clarification questions
    that guide users to provide the needed information.
    
    Args:
        missing_info_type: Type of missing info (task/date/time/datetime)
        collected_task: Already collected task (if any)
        collected_date: Already collected date (if any)
        collected_time: Already collected time (if any)
        user_timezone: User's timezone
        
    Returns:
        Dict with:
            - question: str (the clarification question)
            - examples: list[str] (helpful examples)
            - suggestions: Optional[list] (contextual suggestions)
    """
    try:
        if not settings.GEMINI_API_KEY:
            # Fallback to simple questions
            questions = {
                "task": "What would you like to be reminded of?",
                "date": f"What date should I remind you about '{collected_task or 'this'}'?",
                "time": f"What time should I remind you about '{collected_task or 'this'}'?",
                "datetime": f"When should I remind you about '{collected_task or 'this'}'?"
            }
            return {
                "question": questions.get(missing_info_type, "Please provide more information."),
                "examples": [],
                "suggestions": None
            }
        
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL_NAME,
            temperature=0.7,  # Higher temperature for more natural questions
            google_api_key=settings.GEMINI_API_KEY,
            max_tokens=300
        )
        
        current_datetime = get_current_english_datetime_for_prompt()
        
        prompt = ChatPromptTemplate.from_template("""
You are a helpful AI assistant creating a reminder. You need to ask the user for missing information.

Current datetime: {current_datetime}
User timezone: {user_timezone}

Missing information type: {missing_info_type}
Already collected:
- Task: {collected_task or "None"}
- Date: {collected_date or "None"}
- Time: {collected_time or "None"}

Create a friendly, helpful clarification question that:
1. Is conversational and natural
2. Provides relevant examples based on what's already known
3. Guides the user to provide the needed information
4. Is concise but clear

Respond ONLY with valid JSON:
{{
    "question": "your clarification question",
    "examples": ["example1", "example2", "example3"],
    "suggestions": ["suggestion1", "suggestion2"] or null
}}

Only respond with valid JSON, no other text.
""")
        
        chain = prompt | llm | StrOutputParser()
        
        result = await chain.ainvoke({
            "current_datetime": current_datetime,
            "user_timezone": user_timezone,
            "missing_info_type": missing_info_type,
            "collected_task": collected_task or "None",
            "collected_date": collected_date or "None",
            "collected_time": collected_time or "None"
        })
        
        # Parse JSON response
        try:
            json_str = result.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            parsed_result = json.loads(json_str)
            
            return {
                "question": parsed_result.get("question", "Please provide more information."),
                "examples": parsed_result.get("examples", []),
                "suggestions": parsed_result.get("suggestions")
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM clarification response: {result}, error: {e}")
            # Fallback
            questions = {
                "task": "What would you like to be reminded of?",
                "date": f"What date should I remind you about '{collected_task or 'this'}'?",
                "time": f"What time should I remind you about '{collected_task or 'this'}'?",
                "datetime": f"When should I remind you about '{collected_task or 'this'}'?"
            }
            return {
                "question": questions.get(missing_info_type, "Please provide more information."),
                "examples": [],
                "suggestions": None
            }
            
    except Exception as e:
        logger.error(f"Error in intelligent_clarification_generation: {e}", exc_info=True)
        # Fallback
        questions = {
            "task": "What would you like to be reminded of?",
            "date": f"What date should I remind you about '{collected_task or 'this'}'?",
            "time": f"What time should I remind you about '{collected_task or 'this'}'?",
            "datetime": f"When should I remind you about '{collected_task or 'this'}'?"
        }
        return {
            "question": questions.get(missing_info_type, "Please provide more information."),
            "examples": [],
            "suggestions": None
        }


async def intelligent_error_handling(
    error_type: str,
    error_details: str,
    user_input: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Use LLM to intelligently understand errors and provide helpful responses.
    
    Args:
        error_type: Type of error (parse_error, validation_error, etc.)
        error_details: Detailed error message
        user_input: Original user input that caused the error
        context: Additional context about the error
        
    Returns:
        Dict with:
            - user_message: str (friendly error message for user)
            - suggestions: list[str] (helpful suggestions)
            - can_recover: bool (whether the error can be recovered from)
    """
    try:
        if not settings.GEMINI_API_KEY:
            return {
                "user_message": "Sorry, I encountered an error. Please try again.",
                "suggestions": [],
                "can_recover": False
            }
        
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL_NAME,
            temperature=0.5,
            google_api_key=settings.GEMINI_API_KEY,
            max_tokens=400
        )
        
        prompt = ChatPromptTemplate.from_template("""
You are a helpful AI assistant. An error occurred while processing a user's reminder request.

Error type: {error_type}
Error details: {error_details}
User input: {user_input}
Context: {context}

Your task:
1. Understand what went wrong
2. Create a friendly, helpful error message for the user
3. Provide specific suggestions to fix the issue
4. Determine if the error can be recovered from (user can retry)

Be:
- Friendly and apologetic
- Specific about what went wrong
- Helpful with suggestions
- Encouraging (don't make the user feel bad)

Respond ONLY with valid JSON:
{{
    "user_message": "friendly error message",
    "suggestions": ["suggestion1", "suggestion2", "suggestion3"],
    "can_recover": boolean
}}

Only respond with valid JSON, no other text.
""")
        
        chain = prompt | llm | StrOutputParser()
        
        result = await chain.ainvoke({
            "error_type": error_type,
            "error_details": error_details,
            "user_input": user_input or "No user input provided",
            "context": json.dumps(context) if context else "No additional context"
        })
        
        # Parse JSON response
        try:
            json_str = result.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            parsed_result = json.loads(json_str)
            
            return {
                "user_message": parsed_result.get("user_message", "Sorry, an error occurred. Please try again."),
                "suggestions": parsed_result.get("suggestions", []),
                "can_recover": parsed_result.get("can_recover", False)
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM error handling response: {result}, error: {e}")
            return {
                "user_message": "Sorry, I encountered an error. Please try again.",
                "suggestions": [],
                "can_recover": False
            }
            
    except Exception as e:
        logger.error(f"Error in intelligent_error_handling: {e}", exc_info=True)
        return {
            "user_message": "Sorry, an error occurred. Please try again.",
            "suggestions": [],
            "can_recover": False
        }

