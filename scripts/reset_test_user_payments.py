#!/usr/bin/env python3
"""
Script to reset payment records for test user and make them free tier.
Usage: python scripts/reset_test_user_payments.py [telegram_id]
"""

import sys
import os
import logging
from datetime import datetime

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.database import get_db, init_db
from src.models import User, Payment, SubscriptionTier
from sqlalchemy import and_

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def reset_test_user_payments(telegram_id: int):
    """
    Reset payment records for a test user and make them free tier.
    
    Args:
        telegram_id (int): Telegram user ID to reset
    """
    try:
        # Initialize database
        init_db()
        db = next(get_db())
        
        logger.info(f"Starting payment reset for user {telegram_id}")
        
        # Find the user
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            logger.error(f"User with telegram_id {telegram_id} not found")
            return False
        
        logger.info(f"Found user: {user.username} (ID: {user.id})")
        
        # Get current subscription status
        current_tier = db.query(SubscriptionTier).filter(SubscriptionTier.user_id == user.id).first()
        if current_tier:
            logger.info(f"Current subscription: {current_tier.tier_type} until {current_tier.expires_at}")
        else:
            logger.info("No current subscription found")
        
        # Delete all payment records for this user
        payments = db.query(Payment).filter(Payment.user_id == user.id).all()
        payment_count = len(payments)
        
        if payment_count > 0:
            logger.info(f"Deleting {payment_count} payment records...")
            for payment in payments:
                logger.info(f"  - Deleting payment ID {payment.id} (amount: ${payment.amount/100:.2f}, status: {payment.status})")
                db.delete(payment)
        else:
            logger.info("No payment records found to delete")
        
        # Delete subscription tier record
        if current_tier:
            logger.info(f"Deleting subscription tier record (ID: {current_tier.id})")
            db.delete(current_tier)
        
        # Reset user to free tier
        user.is_premium = False
        user.premium_until = None
        
        # Commit changes
        db.commit()
        
        logger.info(f"✅ Successfully reset user {telegram_id} to free tier")
        logger.info(f"   - Deleted {payment_count} payment records")
        logger.info(f"   - Removed premium subscription")
        logger.info(f"   - User is now free tier (is_premium: {user.is_premium})")
        
        return True
        
    except Exception as e:
        logger.error(f"Error resetting user payments: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def main():
    """Main function to handle command line arguments"""
    if len(sys.argv) != 2:
        print("Usage: python scripts/reset_test_user_payments.py <telegram_id>")
        print("Example: python scripts/reset_test_user_payments.py 27475074")
        sys.exit(1)
    
    try:
        telegram_id = int(sys.argv[1])
    except ValueError:
        print("Error: telegram_id must be a number")
        sys.exit(1)
    
    print(f"🔄 Resetting payment records for test user {telegram_id}...")
    print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("-" * 50)
    
    success = reset_test_user_payments(telegram_id)
    
    if success:
        print("✅ Reset completed successfully!")
        print("🎯 User is now ready for payment testing")
    else:
        print("❌ Reset failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 