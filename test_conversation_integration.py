#!/usr/bin/env python3
"""
Comprehensive test script for conversation flow and context maintenance
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from graph_nodes import parse_datetime_with_llm
from conversation_memory import conversation_memory

async def test_conversation_context():
    """Test conversation context maintenance"""
    
    print("🧪 Testing Conversation Context Maintenance")
    print("=" * 60)
    
    # Simulate a conversation flow
    user_id = 12345
    chat_id = 12345
    session_id = conversation_memory.get_session_id(user_id, chat_id)
    
    # Clear any existing conversation
    conversation_memory.clear_conversation_context(session_id)
    
    # Step 1: User sends initial request
    print("\n📝 Step 1: User sends 'remind me to call by brother'")
    conversation_memory.add_user_message(session_id, "remind me to call by brother")
    
    # Simulate bot response
    bot_response = "Certainly. When should I remind you about 'call by brother'?"
    conversation_memory.add_ai_message(session_id, bot_response)
    
    # Check conversation context
    context = conversation_memory.get_conversation_context(session_id)
    print(f"   Context after Step 1:")
    print(f"   - Has pending clarification: {context['has_pending_clarification']}")
    print(f"   - Pending clarification type: {context['pending_clarification_type']}")
    print(f"   - Collected task: {context['collected_task']}")
    
    # Step 2: User responds with datetime
    print("\n📝 Step 2: User sends 'tommorow 10 AM'")
    conversation_memory.add_user_message(session_id, "tommorow 10 AM")
    
    # Check conversation context again
    context = conversation_memory.get_conversation_context(session_id)
    print(f"   Context after Step 2:")
    print(f"   - Has pending clarification: {context['has_pending_clarification']}")
    print(f"   - Pending clarification type: {context['pending_clarification_type']}")
    print(f"   - Collected task: {context['collected_task']}")
    
    # Test LLM parsing with context
    print("\n📝 Testing LLM parsing with context:")
    try:
        date_str, time_str, input_type = await parse_datetime_with_llm("tommorow 10 AM", "Asia/Tehran")
        print(f"   LLM parsed 'tommorow 10 AM':")
        print(f"   - Date: {date_str}")
        print(f"   - Time: {time_str}")
        print(f"   - Type: {input_type}")
        
        if input_type == "date_time" and date_str and time_str:
            print(f"   ✅ LLM parsing successful!")
            
            # Simulate successful reminder creation
            print(f"\n📝 Step 3: Bot should create reminder for 'call by brother' at {date_str} {time_str}")
            conversation_memory.add_ai_message(session_id, f"Reminder set for 'call by brother' at {date_str} {time_str}")
            
            # Clear conversation after successful creation
            conversation_memory.clear_conversation_context(session_id)
            print(f"   ✅ Conversation completed successfully!")
            
        else:
            print(f"   ❌ LLM parsing failed or returned unexpected type")
            
    except Exception as e:
        print(f"   ❌ Error in LLM parsing: {e}")

async def test_conversation_scenarios():
    """Test different conversation scenarios"""
    
    scenarios = [
        {
            "name": "Scenario 1: Complete datetime response",
            "steps": [
                {"user": "remind me to call by brother", "expected_context": "datetime"},
                {"user": "tommorow 10 AM", "expected_result": "create_reminder"},
            ]
        },
        {
            "name": "Scenario 2: Date only response",
            "steps": [
                {"user": "remind me to call by brother", "expected_context": "datetime"},
                {"user": "nex monday", "expected_result": "ask_for_time"},
            ]
        },
        {
            "name": "Scenario 3: Time only response",
            "steps": [
                {"user": "remind me to call by brother", "expected_context": "datetime"},
                {"user": "morning", "expected_result": "ask_for_date"},
            ]
        },
    ]
    
    print("\n🎭 Testing Conversation Scenarios")
    print("=" * 60)
    
    for scenario in scenarios:
        print(f"\n📋 {scenario['name']}")
        
        # Simulate conversation
        user_id = 12345
        chat_id = 12345
        session_id = conversation_memory.get_session_id(user_id, chat_id)
        conversation_memory.clear_conversation_context(session_id)
        
        for i, step in enumerate(scenario['steps'], 1):
            print(f"   Step {i}: User says '{step['user']}'")
            
            # Add user message
            conversation_memory.add_user_message(session_id, step['user'])
            
            # Check context
            context = conversation_memory.get_conversation_context(session_id)
            
            if i == 1:
                # First step - should set up context
                if context['has_pending_clarification'] and context['collected_task']:
                    print(f"   ✅ Context set up correctly: task='{context['collected_task']}', type='{context['pending_clarification_type']}'")
                else:
                    print(f"   ❌ Context not set up correctly")
                    break
                    
            elif i == 2:
                # Second step - should process datetime
                print(f"   Expected result: {step['expected_result']}")
                
                # Test LLM parsing
                try:
                    date_str, time_str, input_type = await parse_datetime_with_llm(step['user'], "Asia/Tehran")
                    print(f"   LLM result: type='{input_type}', date='{date_str}', time='{time_str}'")
                    
                    if step['expected_result'] == "create_reminder" and input_type == "date_time":
                        print(f"   ✅ Scenario completed successfully!")
                    elif step['expected_result'] == "ask_for_time" and input_type == "date_only":
                        print(f"   ✅ Scenario completed successfully!")
                    elif step['expected_result'] == "ask_for_date" and input_type == "time_only":
                        print(f"   ✅ Scenario completed successfully!")
                    else:
                        print(f"   ❌ Unexpected result")
                        
                except Exception as e:
                    print(f"   ❌ Error: {e}")

async def test_conversation_memory_logic():
    """Test the conversation memory logic directly"""
    
    print("\n🔍 Testing Conversation Memory Logic")
    print("=" * 60)
    
    # Test cases that should NOT be detected as complete reminder requests
    test_cases = [
        "tommorow 10 AM",
        "nex monday",
        "morning",
        "10 AM",
        "today 3:30 PM",
        "next week",
    ]
    
    for test_input in test_cases:
        print(f"\n📝 Testing: '{test_input}'")
        
        # Create a mock conversation context with pending clarification
        user_id = 12345
        chat_id = 12345
        session_id = conversation_memory.get_session_id(user_id, chat_id)
        conversation_memory.clear_conversation_context(session_id)
        
        # First, simulate a bot asking for clarification
        conversation_memory.add_user_message(session_id, "remind me to call my brother")
        conversation_memory.add_ai_message(session_id, "Certainly. When should I remind you about 'call my brother'?")
        
        # Now add the test input as a user message
        conversation_memory.add_user_message(session_id, test_input)
        
        # Check if it's detected as a complete reminder request
        context = conversation_memory.get_conversation_context(session_id)
        
        # This should HAVE pending clarification (meaning it was NOT detected as complete)
        if context['has_pending_clarification']:
            print(f"   ✅ Correct: '{test_input}' was NOT detected as a complete reminder request")
            print(f"   Context preserved: task='{context['collected_task']}', type='{context['pending_clarification_type']}'")
        else:
            print(f"   ❌ PROBLEM: '{test_input}' was detected as a complete reminder request!")
            print(f"   This means the conversation memory logic is incorrect.")

async def main():
    """Main test function"""
    print("🚀 Starting Comprehensive Conversation Flow Test")
    print("=" * 80)
    
    # Test 1: Conversation Context Maintenance
    await test_conversation_context()
    
    # Test 2: Conversation Scenarios
    await test_conversation_scenarios()
    
    # Test 3: Conversation Memory Logic
    await test_conversation_memory_logic()
    
    print("\n" + "=" * 80)
    print("📊 Test Summary:")
    print("   If you see ❌ PROBLEM messages above, the conversation memory logic needs fixing.")
    print("   The bot should maintain context when users provide datetime-only responses.")

if __name__ == "__main__":
    asyncio.run(main()) 