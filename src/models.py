from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Enum as SAEnum, BigInteger, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum
from datetime import datetime, timezone

Base = declarative_base()

class SubscriptionTier(enum.Enum):
    FREE = "FREE"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"

    def __str__(self):
        return self.value

class BaseModel(Base):
    __abstract__ = True
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class User(BaseModel):
    __tablename__ = "users"

    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    language_code = Column(String, default='en')
    timezone = Column(String, default='UTC')  # User's timezone (e.g., "Asia/Tehran", "America/New_York")
    subscription_tier = Column(SAEnum(SubscriptionTier), default=SubscriptionTier.FREE)
    subscription_expiry = Column(DateTime(timezone=True), nullable=True)
    reminder_count = Column(Integer, default=0)
    chat_id = Column(Integer, nullable=True)
    is_admin = Column(Boolean, default=False)  # Admin flag for admin mode features
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username='{self.username}')>"

class Reminder(BaseModel):
    __tablename__ = "reminders"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task = Column(String, nullable=False)
    date_str = Column(String, nullable=True)  # Changed from jalali_date_str
    time_str = Column(String, nullable=True)
    due_datetime_utc = Column(DateTime, nullable=True)
    recurrence_rule = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_notified = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="reminders")

    def __repr__(self):
        return f"<Reminder(id={self.id}, task='{self.task[:20]}...', user_id={self.user_id})>"

    @property
    def datetime_local(self):
        """Get the local datetime from date_str and time_str"""
        try:
            if not self.date_str or not self.time_str:
                return None
            date_obj = datetime.strptime(self.date_str, "%Y-%m-%d").date()
            time_obj = datetime.strptime(self.time_str, "%H:%M").time()
            return datetime.combine(date_obj, time_obj)
        except ValueError:
            # Handle potential parsing errors
            return None

    @datetime_local.setter
    def datetime_local(self, dt: datetime):
        """Set date_str and time_str from a datetime object"""
        self.date_str = dt.strftime("%Y-%m-%d")
        self.time_str = dt.strftime("%H:%M")

    @property
    def gregorian_datetime(self):
        """Get the UTC datetime from due_datetime_utc or construct from date_str and time_str"""
        if self.due_datetime_utc:
            return self.due_datetime_utc
        
        # Try to construct from date_str and time_str if due_datetime_utc is not available
        if self.date_str and self.time_str:
            try:
                from datetime import datetime, timezone
                # Parse date and time strings
                date_obj = datetime.strptime(self.date_str, "%Y-%m-%d").date()
                time_obj = datetime.strptime(self.time_str, "%H:%M").time()
                # Combine and assume UTC
                combined_dt = datetime.combine(date_obj, time_obj)
                return combined_dt.replace(tzinfo=timezone.utc)
            except ValueError as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error constructing datetime from date_str='{self.date_str}' and time_str='{self.time_str}': {e}")
                return None
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Unexpected error constructing datetime for reminder {self.id}: {e}", exc_info=True)
                return None
        
        return None

class Payment(BaseModel):
    __tablename__ = "payments"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    
    track_id = Column(String, unique=True, nullable=False)
    amount = Column(Integer, nullable=False)  # Amount in USD
    status = Column(Integer, nullable=False)  # See PaymentStatus class in payment.py
    
    ref_id = Column(String, nullable=True)  # Reference ID from payment gateway
    card_number = Column(String, nullable=True)  # Masked card number
    
    response_data = Column(Text, nullable=True)  # Raw JSON response from payment gateway
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User")

class MarketingMessage(BaseModel):
    __tablename__ = "marketing_messages"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_type = Column(String, nullable=False)  # 'new_user_3days' or 'inactive_4days'
    sent_at = Column(DateTime(timezone=True), nullable=False)
    sent_to_chat_id = Column(Integer, nullable=False)
    
    # Relationships
    user = relationship("User")
    
    def __repr__(self):
        return f"<MarketingMessage(id={self.id}, user_id={self.user_id}, type='{self.message_type}')>"