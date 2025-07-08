#!/usr/bin/env python3
"""
Deployment verification script for Render.com
This script checks that all required files and configurations are present.
"""
import os
import sys
from pathlib import Path

def check_required_files():
    """Check that all required files for deployment exist."""
    required_files = [
        'app.py',
        'render.yaml',
        'runtime.txt',
        'requirements.txt',
        'src/bot.py',
        'src/payment_callback_server.py',
        'config/config.py'
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
    else:
        print("✅ All required files present")
        return True

def check_environment_variables():
    """Check that environment variables are documented."""
    required_env_vars = [
        'TELEGRAM_BOT_TOKEN',
        'GOOGLE_API_KEY',
        'STRIPE_SECRET_KEY',
        'STRIPE_WEBHOOK_SECRET'
    ]
    
    print("📋 Required environment variables for Render:")
    for var in required_env_vars:
        print(f"   - {var}")
    
    return True

def check_python_version():
    """Check Python version compatibility."""
    try:
        with open('runtime.txt', 'r') as f:
            version = f.read().strip()
        print(f"✅ Python version specified: {version}")
        return True
    except FileNotFoundError:
        print("❌ runtime.txt not found")
        return False

def check_requirements():
    """Check requirements.txt exists and has content."""
    try:
        with open('requirements.txt', 'r') as f:
            content = f.read().strip()
        if content:
            print("✅ requirements.txt is present and has content")
            return True
        else:
            print("❌ requirements.txt is empty")
            return False
    except FileNotFoundError:
        print("❌ requirements.txt not found")
        return False

def main():
    """Main verification function."""
    print("🔍 Verifying deployment configuration for Render.com...")
    print()
    
    checks = [
        ("Required Files", check_required_files),
        ("Python Version", check_python_version),
        ("Requirements", check_requirements),
        ("Environment Variables", check_environment_variables)
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        if not check_func():
            all_passed = False
    
    print("\n" + "="*50)
    if all_passed:
        print("🎉 All checks passed! Your project is ready for Render deployment.")
        print("\nNext steps:")
        print("1. Push your code to GitHub")
        print("2. Connect your repository to Render.com")
        print("3. Set up environment variables in Render dashboard")
        print("4. Deploy!")
    else:
        print("❌ Some checks failed. Please fix the issues above before deploying.")
        sys.exit(1)

if __name__ == "__main__":
    main() 