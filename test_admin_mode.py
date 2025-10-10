#!/usr/bin/env python3
"""
Test script for admin mode functionality.

This script tests the admin mode features without requiring a running bot.
"""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import init_db, get_db
from src.models import User, SubscriptionTier
from src.admin import is_user_admin, set_user_admin, get_all_admins, get_user_stats

def test_admin_functionality():
    """Test the admin functionality."""
    print("🧪 Testing Admin Mode Functionality")
    print("=" * 50)
    
    # Initialize database
    init_db()
    
    # Create a test user
    db = next(get_db())
    test_user = User(
        telegram_id=123456789,
        first_name="Test",
        last_name="User",
        username="testuser",
        language_code="en",
        subscription_tier=SubscriptionTier.FREE
    )
    
    try:
        # Check if user exists, if not create it
        existing_user = db.query(User).filter(User.telegram_id == 123456789).first()
        if not existing_user:
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            print("✅ Created test user")
        else:
            test_user = existing_user
            print("✅ Using existing test user")
        
        # Test 1: Check admin status (should be False initially)
        print("\n1. Testing initial admin status...")
        is_admin = is_user_admin(123456789)
        print(f"   User is admin: {is_admin} (Expected: False)")
        assert not is_admin, "User should not be admin initially"
        print("   ✅ PASS")
        
        # Test 2: Set user as admin
        print("\n2. Testing setting admin status...")
        success = set_user_admin(123456789, True)
        print(f"   Set admin status: {success} (Expected: True)")
        assert success, "Should be able to set admin status"
        print("   ✅ PASS")
        
        # Test 3: Check admin status again (should be True now)
        print("\n3. Testing admin status after setting...")
        is_admin = is_user_admin(123456789)
        print(f"   User is admin: {is_admin} (Expected: True)")
        assert is_admin, "User should be admin now"
        print("   ✅ PASS")
        
        # Test 4: Get all admins
        print("\n4. Testing get all admins...")
        admins = get_all_admins()
        print(f"   Number of admins: {len(admins)} (Expected: 1)")
        assert len(admins) == 1, "Should have exactly 1 admin"
        assert admins[0].telegram_id == 123456789, "Admin should be our test user"
        print("   ✅ PASS")
        
        # Test 5: Get user stats
        print("\n5. Testing user statistics...")
        stats = get_user_stats()
        print(f"   Total users: {stats.get('total_users', 0)}")
        print(f"   Premium users: {stats.get('premium_users', 0)}")
        print(f"   Free users: {stats.get('free_users', 0)}")
        print(f"   Total reminders: {stats.get('total_reminders', 0)}")
        assert stats.get('total_users', 0) >= 1, "Should have at least 1 user"
        print("   ✅ PASS")
        
        # Test 6: Remove admin status
        print("\n6. Testing removing admin status...")
        success = set_user_admin(123456789, False)
        print(f"   Remove admin status: {success} (Expected: True)")
        assert success, "Should be able to remove admin status"
        
        is_admin = is_user_admin(123456789)
        print(f"   User is admin after removal: {is_admin} (Expected: False)")
        assert not is_admin, "User should not be admin after removal"
        print("   ✅ PASS")
        
        print("\n🎉 All tests passed! Admin mode functionality is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    test_admin_functionality()
