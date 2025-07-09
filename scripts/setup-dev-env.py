#!/usr/bin/env python3
"""
Development Environment Setup Script
Helps configure the bot for Render.com + Supabase development deployment
"""
import os
import sys
from pathlib import Path

def create_env_file():
    """Create .env file from template if it doesn't exist"""
    env_file = Path(".env")
    env_sample = Path("env.sample")
    
    if env_file.exists():
        print("✅ .env file already exists")
        return
    
    if not env_sample.exists():
        print("❌ env.sample not found")
        return
    
    # Copy env.sample to .env
    with open(env_sample, 'r') as f:
        content = f.read()
    
    with open(env_file, 'w') as f:
        f.write(content)
    
    print("✅ Created .env file from env.sample")
    print("📝 Please edit .env with your actual values")

def check_requirements():
    """Check if all required files exist"""
    required_files = [
        "requirements.txt",
        "runtime.txt", 
        "app.py",
        "src/",
        "render.yaml"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        return False
    
    print("✅ All required files found")
    return True

def validate_env_vars():
    """Check if critical environment variables are set"""
    critical_vars = [
        "TELEGRAM_BOT_TOKEN",
        "DATABASE_URL", 
        "GEMINI_API_KEY"
    ]
    
    missing_vars = []
    for var in critical_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("⚠️  Missing critical environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n📝 Please set these in your .env file or Render dashboard")
        return False
    
    print("✅ All critical environment variables are set")
    return True

def print_next_steps():
    """Print next steps for setup"""
    print("\n" + "="*50)
    print("🚀 NEXT STEPS FOR DEVELOPMENT SETUP")
    print("="*50)
    
    print("\n1. 📊 SUPABASE SETUP:")
    print("   - Go to https://supabase.com/dashboard")
    print("   - Create new project: telegram-reminder-bot-dev")
    print("   - Copy database connection details")
    print("   - Update DATABASE_URL in .env or Render dashboard")
    
    print("\n2. 🌐 RENDER.COM SETUP:")
    print("   - Go to https://dashboard.render.com")
    print("   - Create new Web Service")
    print("   - Connect your GitHub repository")
    print("   - Set environment variables in Render dashboard")
    
    print("\n3. 🤖 TELEGRAM BOT:")
    print("   - Get bot token from @BotFather")
    print("   - Set TELEGRAM_BOT_TOKEN in environment")
    
    print("\n4. 🧠 GEMINI AI:")
    print("   - Get API key from Google AI Studio")
    print("   - Set GEMINI_API_KEY in environment")
    
    print("\n5. 🧪 TEST DEPLOYMENT:")
    print("   - Deploy on Render")
    print("   - Test bot functionality")
    print("   - Check database tables in Supabase")
    
    print("\n📚 For detailed instructions, see: docs/setup-render-supabase.md")

def main():
    print("🔧 Telegram Reminder Bot - Development Setup")
    print("="*50)
    
    # Check requirements
    if not check_requirements():
        print("\n❌ Setup cannot continue. Please ensure all required files exist.")
        sys.exit(1)
    
    # Create .env file
    create_env_file()
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Validate environment
    validate_env_vars()
    
    # Print next steps
    print_next_steps()

if __name__ == "__main__":
    main() 