#!/usr/bin/env python3
"""
Admin Setup Script

This script helps set up the first admin user for the Telegram Reminder Bot.
Run this script to make a user an admin or to check admin status.
"""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.database import init_db, get_db
from src.models import User
from src.admin import is_user_admin, set_user_admin, get_all_admins

def setup_first_admin():
    """Interactive script to set up the first admin user."""
    print("🔧 Telegram Reminder Bot - Admin Setup")
    print("=" * 50)
    
    # Initialize database
    init_db()
    
    # Check if there are any existing admins
    existing_admins = get_all_admins()
    
    if existing_admins:
        print(f"✅ Found {len(existing_admins)} existing admin(s):")
        for admin in existing_admins:
            print(f"  • {admin.first_name} {admin.last_name or ''} (@{admin.username or 'N/A'}) - ID: {admin.telegram_id}")
        print()
    
    while True:
        print("\nOptions:")
        print("1. Make a user an admin")
        print("2. Remove admin status from a user")
        print("3. Check if a user is admin")
        print("4. List all admins")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == '1':
            try:
                user_id = int(input("Enter Telegram user ID: "))
                success = set_user_admin(user_id, True)
                if success:
                    print(f"✅ User {user_id} is now an admin!")
                else:
                    print(f"❌ Failed to set admin status. User {user_id} may not exist.")
            except ValueError:
                print("❌ Invalid user ID. Please enter a number.")
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == '2':
            try:
                user_id = int(input("Enter Telegram user ID: "))
                success = set_user_admin(user_id, False)
                if success:
                    print(f"✅ Admin status removed from user {user_id}")
                else:
                    print(f"❌ Failed to remove admin status. User {user_id} may not exist.")
            except ValueError:
                print("❌ Invalid user ID. Please enter a number.")
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == '3':
            try:
                user_id = int(input("Enter Telegram user ID: "))
                is_admin = is_user_admin(user_id)
                status = "✅ IS" if is_admin else "❌ IS NOT"
                print(f"User {user_id} {status} an admin")
            except ValueError:
                print("❌ Invalid user ID. Please enter a number.")
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == '4':
            admins = get_all_admins()
            if admins:
                print(f"\n📋 All Admin Users ({len(admins)}):")
                for admin in admins:
                    print(f"  • {admin.first_name} {admin.last_name or ''} (@{admin.username or 'N/A'}) - ID: {admin.telegram_id}")
            else:
                print("❌ No admin users found.")
        
        elif choice == '5':
            print("👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice. Please enter 1-5.")

def quick_admin_setup(user_id: int):
    """Quick setup to make a user admin (for command line usage)."""
    init_db()
    
    success = set_user_admin(user_id, True)
    if success:
        print(f"✅ User {user_id} is now an admin!")
        return True
    else:
        print(f"❌ Failed to set admin status. User {user_id} may not exist.")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line usage: python setup_admin.py <user_id>
        try:
            user_id = int(sys.argv[1])
            quick_admin_setup(user_id)
        except ValueError:
            print("❌ Invalid user ID. Please provide a valid Telegram user ID.")
            print("Usage: python setup_admin.py <telegram_user_id>")
    else:
        # Interactive mode
        setup_first_admin()
