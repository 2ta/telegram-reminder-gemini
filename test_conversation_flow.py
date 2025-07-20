#!/usr/bin/env python3
"""
Test script for conversation flow and LLM datetime parsing
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from graph_nodes import parse_datetime_with_llm

async def test_llm_datetime_parsing():
    """Test the LLM datetime parsing with various inputs"""
    
    test_cases = [
        ("tommorow 10 AM", "Asia/Tehran"),
        ("nex monday morning", "Asia/Tehran"),
        ("today 3:30 PM", "Asia/Tehran"),
        ("next week", "Asia/Tehran"),
        ("10 AM", "Asia/Tehran"),
        ("morning", "Asia/Tehran"),
        ("tuesdy afternoon", "Asia/Tehran"),
        ("invalid input", "Asia/Tehran"),
    ]
    
    print("🧪 Testing LLM Datetime Parsing")
    print("=" * 50)
    
    success_count = 0
    total_count = len(test_cases)
    
    for input_text, timezone in test_cases:
        print(f"\n📝 Input: '{input_text}' (Timezone: {timezone})")
        try:
            date_str, time_str, input_type = await parse_datetime_with_llm(input_text, timezone)
            print(f"   ✅ Date: {date_str}")
            print(f"   ✅ Time: {time_str}")
            print(f"   ✅ Type: {input_type}")
            
            # Validate the result
            if input_type == "date_time":
                if date_str and time_str:
                    print(f"   🎯 RESULT: Complete datetime parsed successfully!")
                    success_count += 1
                else:
                    print(f"   ❌ ERROR: date_time type but missing date or time")
            elif input_type == "date_only":
                if date_str and not time_str:
                    print(f"   🎯 RESULT: Date-only parsed successfully!")
                    success_count += 1
                else:
                    print(f"   ❌ ERROR: date_only type but missing date or has time")
            elif input_type == "time_only":
                if time_str and not date_str:
                    print(f"   🎯 RESULT: Time-only parsed successfully!")
                    success_count += 1
                else:
                    print(f"   ❌ ERROR: time_only type but missing time or has date")
            elif input_type == "unclear":
                print(f"   ⚠️  RESULT: Input unclear - this is expected for invalid inputs")
                if input_text == "invalid input":
                    success_count += 1  # This is expected to be unclear
            else:
                print(f"   ❌ ERROR: Unknown input type: {input_type}")
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
    
    print("\n" + "=" * 50)
    print(f"🏁 Test completed! Success rate: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    
    return success_count >= total_count * 0.8  # 80% success rate threshold

def test_conversation_scenarios():
    """Test the expected conversation scenarios"""
    
    scenarios = [
        {
            "name": "Scenario 1: Complete datetime input",
            "steps": [
                {"user": "remind me to call by brother", "expected_bot": "When should I remind you about 'call by brother'?"},
                {"user": "tommorow 10 AM", "expected_bot": "should create reminder successfully"},
            ]
        },
        {
            "name": "Scenario 2: Date only input",
            "steps": [
                {"user": "remind me to call by brother", "expected_bot": "When should I remind you about 'call by brother'?"},
                {"user": "nex monday", "expected_bot": "should ask for time"},
            ]
        },
        {
            "name": "Scenario 3: Time only input",
            "steps": [
                {"user": "remind me to call by brother", "expected_bot": "When should I remind you about 'call by brother'?"},
                {"user": "morning", "expected_bot": "should ask for date"},
            ]
        },
    ]
    
    print("\n🎭 Testing Conversation Scenarios")
    print("=" * 50)
    
    for scenario in scenarios:
        print(f"\n📋 {scenario['name']}")
        for i, step in enumerate(scenario['steps'], 1):
            print(f"   Step {i}: User says '{step['user']}'")
            print(f"   Expected: Bot {step['expected_bot']}")
    
    print("\n" + "=" * 50)
    print("💡 Manual Testing Instructions:")
    print("1. Send 'remind me to call by brother' to the bot")
    print("2. When bot asks for time, send 'tommorow 10 AM'")
    print("3. Bot should create the reminder successfully")
    print("4. Test other scenarios: 'nex monday', 'morning', etc.")

async def main():
    """Main test function"""
    print("🚀 Starting Comprehensive Bot Test")
    print("=" * 60)
    
    # Test 1: LLM Datetime Parsing
    llm_success = await test_llm_datetime_parsing()
    
    # Test 2: Conversation Scenarios
    test_conversation_scenarios()
    
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    print(f"   LLM Datetime Parsing: {'✅ PASSED' if llm_success else '❌ FAILED'}")
    print(f"   Conversation Flow: ⏳ MANUAL TESTING REQUIRED")
    
    if llm_success:
        print("\n🎉 LLM datetime parsing is working! You can now test the bot manually.")
        print("📱 Try the conversation scenarios above with your Telegram bot.")
    else:
        print("\n⚠️  LLM datetime parsing has issues. Please check the logs and fix before testing.")

if __name__ == "__main__":
    asyncio.run(main()) 