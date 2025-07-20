#!/usr/bin/env python3
"""
Database Reset Script for Testing
This script clears all user data and reminders from the database.
Use with caution - this will delete all data!
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import get_db, init_db
from src.models import User, Reminder, Payment
from sqlalchemy import text
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    """Reset all user data and reminders from the database."""
    try:
        # Initialize database connection
        db = next(get_db())
        
        logger.info("Starting database reset...")
        
        # Delete all reminders
        reminder_count = db.query(Reminder).count()
        db.query(Reminder).delete()
        logger.info(f"Deleted {reminder_count} reminders")
        
        # Delete all payments
        payment_count = db.query(Payment).count()
        db.query(Payment).delete()
        logger.info(f"Deleted {payment_count} payments")
        
        # Delete all users
        user_count = db.query(User).count()
        db.query(User).delete()
        logger.info(f"Deleted {user_count} users")
        
        # Reset auto-increment counters (PostgreSQL syntax)
        db.execute(text("ALTER SEQUENCE reminders_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE payments_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE users_id_seq RESTART WITH 1"))
        
        # Commit the changes
        db.commit()
        
        logger.info("Database reset completed successfully!")
        logger.info(f"Summary: {user_count} users, {reminder_count} reminders, {payment_count} payments deleted")
        
    except Exception as e:
        logger.error(f"Error during database reset: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("WARNING: This will delete ALL user data, reminders, and payments!")
    print("Are you sure you want to continue? (yes/no): ", end="")
    
    response = input().strip().lower()
    if response == "yes":
        reset_database()
        print("Database reset completed!")
    else:
        print("Database reset cancelled.") 