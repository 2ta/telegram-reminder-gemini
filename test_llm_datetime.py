#!/usr/bin/env python3
"""
Test script for LLM datetime parsing functionality
"""

import asyncio
import sys
import os

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
                else:
                    print(f"   ❌ ERROR: date_time type but missing date or time")
            elif input_type == "date_only":
                if date_str and not time_str:
                    print(f"   🎯 RESULT: Date-only parsed successfully!")
                else:
                    print(f"   ❌ ERROR: date_only type but missing date or has time")
            elif input_type == "time_only":
                if time_str and not date_str:
                    print(f"   🎯 RESULT: Time-only parsed successfully!")
                else:
                    print(f"   ❌ ERROR: time_only type but missing time or has date")
            elif input_type == "unclear":
                print(f"   ⚠️  RESULT: Input unclear - this is expected for invalid inputs")
            else:
                print(f"   ❌ ERROR: Unknown input type: {input_type}")
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Test completed!")

if __name__ == "__main__":
    asyncio.run(test_llm_datetime_parsing()) 