import logging
from typing import Dict, Any, List
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class ConversationMemoryManager:
    """Manages conversation memory for the reminder bot using LangChain's message history."""
    
    def __init__(self, storage_path: str = "./conversation_memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self._conversations: Dict[str, ChatMessageHistory] = {}
    
    def get_session_id(self, user_id: int, chat_id: int) -> str:
        """Generate a unique session ID for the user."""
        return f"user_{user_id}_chat_{chat_id}"
    
    def get_message_history(self, session_id: str) -> ChatMessageHistory:
        """Get or create message history for a session."""
        if session_id not in self._conversations:
            # Try to load from file
            file_path = self.storage_path / f"{session_id}.json"
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    history = ChatMessageHistory()
                    for msg_data in data.get('messages', []):
                        if msg_data['type'] == 'human':
                            history.add_user_message(msg_data['content'])
                        elif msg_data['type'] == 'ai':
                            history.add_ai_message(msg_data['content'])
                    self._conversations[session_id] = history
                    logger.info(f"Loaded conversation history for session {session_id}")
                except Exception as e:
                    logger.error(f"Error loading conversation history for {session_id}: {e}")
                    self._conversations[session_id] = ChatMessageHistory()
            else:
                self._conversations[session_id] = ChatMessageHistory()
        
        return self._conversations[session_id]
    
    def save_message_history(self, session_id: str):
        """Save message history to file."""
        if session_id in self._conversations:
            history = self._conversations[session_id]
            file_path = self.storage_path / f"{session_id}.json"
            try:
                messages = []
                for msg in history.messages:
                    if isinstance(msg, HumanMessage):
                        messages.append({"type": "human", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        messages.append({"type": "ai", "content": msg.content})
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({"messages": messages}, f, indent=2, ensure_ascii=False)
                logger.debug(f"Saved conversation history for session {session_id}")
            except Exception as e:
                logger.error(f"Error saving conversation history for {session_id}: {e}")
    
    def add_user_message(self, session_id: str, content: str):
        """Add a user message to the conversation history."""
        history = self.get_message_history(session_id)
        history.add_user_message(content)
        self.save_message_history(session_id)
    
    def add_ai_message(self, session_id: str, content: str):
        """Add an AI message to the conversation history."""
        history = self.get_message_history(session_id)
        history.add_ai_message(content)
        self.save_message_history(session_id)
    
    def get_conversation_context(self, session_id: str) -> Dict[str, Any]:
        """Get conversation context including reminder creation state."""
        history = self.get_message_history(session_id)
        
        # Extract reminder creation context from recent messages
        context = {
            "has_pending_clarification": False,
            "pending_clarification_type": None,
            "collected_task": None,
            "collected_date_str": None,
            "collected_time_str": None,
            "last_question": None
        }
        
        # Look for recent clarification patterns
        recent_messages = history.messages[-4:] if len(history.messages) >= 4 else history.messages
        
        for i, msg in enumerate(recent_messages):
            if isinstance(msg, AIMessage):
                content = msg.content.lower()
                if "when should i remind you" in content:
                    context["has_pending_clarification"] = True
                    context["pending_clarification_type"] = "datetime"
                    # Extract task from the question
                    if "about '" in content and "'?" in content:
                        task_start = content.find("about '") + 7
                        task_end = content.find("'?", task_start)
                        if task_start > 6 and task_end > task_start:
                            context["collected_task"] = content[task_start:task_end]
                    context["last_question"] = msg.content
                elif "what would you like to be reminded of" in content:
                    context["has_pending_clarification"] = True
                    context["pending_clarification_type"] = "task"
                    context["last_question"] = msg.content
        
        return context
    
    def clear_conversation(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self._conversations:
            del self._conversations[session_id]
        
        # Remove file
        file_path = self.storage_path / f"{session_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Cleared conversation history for session {session_id}")
            except Exception as e:
                logger.error(f"Error clearing conversation history for {session_id}: {e}")

# Global instance
conversation_memory = ConversationMemoryManager() 