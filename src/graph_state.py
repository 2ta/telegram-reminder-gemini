from typing import TypedDict, List, Optional, Annotated, Dict, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage # Assuming BaseMessage is used with add_messages
import datetime

# Reminder: Ensure all Message constants used in bot.py (MSG_*) are defined,
# ideally in a dedicated config/messages.py or similar, and imported correctly.

class AgentState(TypedDict):
    """Represents the state of our LangGraph agent."""

    # Core Identifiers
    user_id: Optional[int]
    chat_id: Optional[int]
    # message_id: Optional[int] # ID of the incoming message, for context or replies
    # last_bot_message_id: Optional[int] # ID of the last message sent by the bot, for edits

    # Input Processing
    input_text: Optional[str]                   # Raw text from user or command arguments
    transcribed_text: Optional[str]             # Output from STT if input was voice
    # telegram_update_json: Optional[str]       # Full update object as JSON string if needed for deep inspection by tools

    # Conversation History & NLU
    # messages: Annotated[List[BaseMessage], add_messages] # For full LCEL message history (Human, AI, System)
    # Simplified for now if full BaseMessage objects aren't immediately needed by all nodes:
    conversation_history: Optional[List[Dict[str, str]]] # List of {"speaker": "user/bot", "text": "..."}
    
    current_intent: Optional[str]               # Primary intent from NLU (e.g., 'create_reminder', 'list_reminders')
    extracted_parameters: Optional[Dict[str, Any]] # Parameters directly from primary NLU (e.g., task, date, time for creation)
    nlu_direct_output: Optional[Dict[str, Any]]   # Raw JSON output from Gemini NLU for inspection or complex handling

    # Reminder Creation Context (for multi-turn creation)
    reminder_creation_context: Optional[Dict[str, Any]] # Holds state for creating a reminder:
                                                        # "status": "clarification_needed" | "ready_for_confirmation" | "confirmed"
                                                        # "pending_clarification_type": "task" | "datetime" | "am_pm" | None
                                                        # "collected_task": Optional[str]
                                                        # "collected_date_str": Optional[str]
                                                        # "collected_time_str": Optional[str]
                                                        # "collected_parsed_datetime_utc": Optional[datetime.datetime]
                                                        # "ambiguous_time_details": Optional[Dict] (e.g., hour, minute for AM/PM)
                                                        # "original_user_input_for_nlu": Optional[str] (the input that triggered create_reminder)
                                                        # "last_question_asked": Optional[str] (e.g. "ask_task", "ask_datetime")
    pending_confirmation: Optional[str] = None          # Signifies if the bot is waiting for a Yes/No confirmation.
                                                        # e.g., "create_reminder", "delete_reminder"

    # Reminder Viewing/Filtering Context
    reminder_filters: Optional[Dict[str, Any]]  # For list filtering:
                                                # raw_date_phrase: Optional[str]
                                                # keywords: Optional[List[str]]
                                                # date_start_utc: Optional[datetime.datetime]
                                                # date_end_utc: Optional[datetime.datetime]
    active_reminders_page: int                  # Current page for paginated reminder lists (default 0)

    # Reminder Action Context (Edit/Delete/Snooze)
    target_reminder_id: Optional[int]           # ID of the reminder being acted upon
    # ambiguous_reminders_for_action: Optional[List[Dict[str, Any]]] # If multiple match, for user choice
    # reminder_action_status: Optional[str]     # Detailed status of the action

    # Payment Context
    payment_context: Optional[Dict[str, Any]]   # track_id: Optional[str]
                                                # amount: Optional[int]
                                                # status: Optional[str] (e.g., from PaymentStatus enum)
                                                # payment_url: Optional[str]
                                                # zibal_ref_id: Optional[str]

    # User Profile (loaded at start of graph run, or updated after payment)
    user_profile: Optional[Dict[str, Any]]      # user_db_id: int
                                                # is_premium: bool
                                                # premium_until: Optional[datetime.datetime]
                                                # language_code: Optional[str]
                                                # reminder_limit: int
                                                # current_reminder_count: int

    # Graph Execution & Output
    current_operation_status: Optional[str]     # General status: "success", "failure", "clarification_needed", "awaiting_user_input", "pending_external_action"
    response_text: Optional[str]                # Message to be sent to the user by the bot
    response_keyboard_markup: Optional[Dict[str, Any]] # For inline/reply keyboards (serializable)
    error_message: Optional[str]                # If an error occurred, for logging or user display
    # next_handler_key: Optional[str]           # For compatibility if needing to jump to non-LangGraph handlers (to be phased out)
    # current_node_name: Optional[str]          # Auto-populated by some LangGraph setups, or can be set manually

# Example of how conversation_history could be structured if not using BaseMessage directly:
# HistoryMessage = TypedDict("HistoryMessage", {"speaker": Literal["user", "bot", "system"], "text": str})
# conversation_history: Optional[List[HistoryMessage]] 