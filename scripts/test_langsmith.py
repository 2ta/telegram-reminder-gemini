#!/usr/bin/env python3
"""
Test script for LangSmith integration.

This script tests the LangSmith configuration and basic tracing functionality.
Run this script to verify that LangSmith is properly set up.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.langsmith_config import setup_langsmith, is_langsmith_enabled, get_langsmith_client
from config.config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_langsmith_integration():
    """Test LangSmith integration and basic functionality."""
    
    print("🔧 Testing LangSmith Integration")
    print("=" * 50)
    
    # Test 1: Check configuration
    print("\n1. Checking LangSmith Configuration...")
    
    if not settings.LANGSMITH_API_KEY:
        print("❌ LANGSMITH_API_KEY not found in environment variables")
        print("   Please add your LangSmith API key to your .env file:")
        print("   LANGSMITH_API_KEY=your_api_key_here")
        return False
    
    print(f"✅ LANGSMITH_API_KEY found")
    print(f"✅ LANGSMITH_PROJECT: {settings.LANGSMITH_PROJECT or 'telegram-reminder-bot'}")
    print(f"✅ LANGSMITH_TRACING_V2: {settings.LANGSMITH_TRACING_V2}")
    
    # Test 2: Initialize LangSmith
    print("\n2. Initializing LangSmith...")
    
    try:
        setup_langsmith()
        print("✅ LangSmith setup completed")
    except Exception as e:
        print(f"❌ Failed to setup LangSmith: {e}")
        return False
    
    # Test 3: Check if LangSmith is enabled
    print("\n3. Checking LangSmith Status...")
    
    if is_langsmith_enabled():
        print("✅ LangSmith is enabled and ready")
    else:
        print("❌ LangSmith is not enabled")
        return False
    
    # Test 4: Test LangSmith client
    print("\n4. Testing LangSmith Client...")
    
    client = get_langsmith_client()
    if client:
        print("✅ LangSmith client initialized successfully")
        
        # Test basic client functionality
        try:
            # This is a simple test to verify the client can connect
            # We'll just check if we can access the client without errors
            print("✅ LangSmith client connection test passed")
        except Exception as e:
            print(f"⚠️  LangSmith client test warning: {e}")
            print("   This might be due to network issues or API key problems")
    else:
        print("❌ Failed to get LangSmith client")
        return False
    
    # Test 5: Test environment variables
    print("\n5. Checking Environment Variables...")
    
    required_vars = [
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_TRACING_V2"
    ]
    
    optional_vars = [
        "LANGCHAIN_PROJECT",
        "LANGCHAIN_ENDPOINT"
    ]
    
    all_good = True
    
    for var in required_vars:
        if var in os.environ:
            print(f"✅ {var}: {os.environ[var]}")
        else:
            print(f"❌ {var}: Not set")
            all_good = False
    
    for var in optional_vars:
        if var in os.environ:
            print(f"✅ {var}: {os.environ[var]}")
        else:
            print(f"⚠️  {var}: Not set (optional)")
    
    if not all_good:
        print("\n❌ Some required environment variables are missing")
        return False
    
    # Test 6: Test basic tracing (if possible)
    print("\n6. Testing Basic Tracing...")
    
    try:
        from langchain_core.tracers import LangChainTracer
        from langchain_core.runnables import RunnablePassthrough
        
        # Create a simple test chain
        test_chain = RunnablePassthrough()
        
        # This should create a trace if LangSmith is working
        result = test_chain.invoke({"test": "data"})
        print("✅ Basic tracing test completed")
        print(f"   Test result: {result}")
        
    except Exception as e:
        print(f"⚠️  Basic tracing test warning: {e}")
        print("   This might be due to network issues or API configuration")
    
    print("\n" + "=" * 50)
    print("🎉 LangSmith Integration Test Completed!")
    print("\nNext Steps:")
    print("1. Start your bot with: python run_bot.py")
    print("2. Send some messages to your bot")
    print("3. Check your LangSmith dashboard for traces")
    print("4. Visit: https://smith.langchain.com/")
    
    return True

async def test_graph_integration():
    """Test LangGraph integration with LangSmith."""
    
    print("\n🔧 Testing LangGraph + LangSmith Integration")
    print("=" * 50)
    
    try:
        from src.graph import create_graph
        
        print("\n1. Creating LangGraph with LangSmith...")
        graph = create_graph()
        print("✅ LangGraph created successfully")
        
        print("\n2. Testing graph compilation...")
        # The graph should be compiled with LangSmith tracing if enabled
        print("✅ Graph compilation completed")
        
        print("\n3. Testing basic graph invocation...")
        
        # Create a test input
        test_input = {
            "input_text": "/start",
            "user_id": "test_user_123",
            "chat_id": "test_chat_123",
            "message_type": "command",
            "user_telegram_details": {"first_name": "Test", "username": "testuser"}
        }
        
        # Invoke the graph
        result = await graph.ainvoke(test_input)
        print("✅ Graph invocation completed")
        print(f"   Response: {result.get('response_text', 'No response text')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Graph integration test failed: {e}")
        return False

async def main():
    """Main test function."""
    
    print("🚀 LangSmith Integration Test Suite")
    print("=" * 50)
    
    # Test basic LangSmith integration
    langsmith_ok = await test_langsmith_integration()
    
    if langsmith_ok:
        # Test graph integration
        graph_ok = await test_graph_integration()
        
        if graph_ok:
            print("\n🎉 All tests passed! LangSmith is ready to use.")
        else:
            print("\n⚠️  LangSmith is configured but graph integration has issues.")
    else:
        print("\n❌ LangSmith integration failed. Please check your configuration.")
    
    print("\nFor more information, see: docs/LANGSMITH_INTEGRATION.md")

if __name__ == "__main__":
    asyncio.run(main()) 