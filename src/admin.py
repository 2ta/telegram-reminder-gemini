"""
Admin management module for the Telegram Reminder Bot.

This module provides functionality for managing admin users and sending
notifications when new users register.
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.error import TelegramError

from src.database import get_db
from src.models import User
from config.config import settings

logger = logging.getLogger(__name__)

def is_user_admin(telegram_id: int) -> bool:
    """Check if a user is an admin."""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        return user.is_admin if user else False
    except Exception as e:
        logger.error(f"Error checking admin status for user {telegram_id}: {e}")
        return False
    finally:
        db.close()

def set_user_admin(telegram_id: int, is_admin: bool = True) -> bool:
    """Set or unset admin status for a user."""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            logger.warning(f"User {telegram_id} not found when setting admin status")
            return False
        
        user.is_admin = is_admin
        db.commit()
        logger.info(f"Set admin status for user {telegram_id} to {is_admin}")
        return True
    except Exception as e:
        logger.error(f"Error setting admin status for user {telegram_id}: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def get_all_admins() -> List[User]:
    """Get all admin users."""
    db = next(get_db())
    try:
        # Use explicit boolean comparison for PostgreSQL compatibility
        admins = db.query(User).filter(User.is_admin.is_(True)).all()
        return admins
    except Exception as e:
        logger.error(f"Error getting admin users: {e}")
        return []
    finally:
        db.close()

async def send_admin_notification(bot: Bot, new_user: User, notification_type: str = "new_user") -> None:
    """Send notification to all admin users about a new user registration."""
    try:
        admins = get_all_admins()
        if not admins:
            logger.info("No admin users found, skipping notification")
            return
        
        # Create notification message
        if notification_type == "new_user":
            message = (
                "🔔 **New User Registration Alert**\n\n"
                f"👤 **User Details:**\n"
                f"• Name: {new_user.first_name}"
                f"{' ' + new_user.last_name if new_user.last_name else ''}\n"
                f"• Username: @{new_user.username if new_user.username else 'N/A'}\n"
                f"• Telegram ID: `{new_user.telegram_id}`\n"
                f"• Language: {new_user.language_code}\n"
                f"• Timezone: {new_user.timezone}\n"
                f"• Registration Time: {new_user.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                f"📊 **Bot Statistics:**\n"
                f"• Total Users: {get_total_user_count()}\n"
                f"• Active Reminders: {get_total_reminder_count()}"
            )
        else:
            message = f"🔔 Admin notification: {notification_type}"
        
        # Send notification to all admins
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.telegram_id,
                    text=message,
                    parse_mode='Markdown'
                )
                logger.info(f"Sent admin notification to admin {admin.telegram_id}")
            except TelegramError as e:
                logger.error(f"Failed to send notification to admin {admin.telegram_id}: {e}")
        
        logger.info(f"Admin notifications sent for {notification_type}")
        
    except Exception as e:
        logger.error(f"Error sending admin notifications: {e}")

def get_total_user_count() -> int:
    """Get total number of users."""
    db = next(get_db())
    try:
        count = db.query(User).count()
        return count
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        return 0
    finally:
        db.close()

def get_total_reminder_count() -> int:
    """Get total number of active reminders."""
    from src.models import Reminder
    db = next(get_db())
    try:
        count = db.query(Reminder).filter(Reminder.is_active == True).count()
        return count
    except Exception as e:
        logger.error(f"Error getting reminder count: {e}")
        return 0
    finally:
        db.close()

def get_user_stats() -> dict:
    """Get comprehensive user statistics for admin dashboard."""
    db = next(get_db())
    try:
        from src.models import Reminder
        
        total_users = db.query(User).count()
        premium_users = db.query(User).filter(User.subscription_tier != 'FREE').count()
        free_users = db.query(User).filter(User.subscription_tier == 'FREE').count()
        total_reminders = db.query(Reminder).filter(Reminder.is_active == True).count()
        
        # Recent registrations (last 24 hours)
        from datetime import datetime, timedelta, timezone
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        recent_users = db.query(User).filter(User.created_at >= yesterday).count()
        
        return {
            'total_users': total_users,
            'premium_users': premium_users,
            'free_users': free_users,
            'total_reminders': total_reminders,
            'recent_registrations': recent_users
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {}
    finally:
        db.close()
