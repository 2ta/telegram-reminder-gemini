from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Enum as SAEnum, BigInteger, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum
import jdatetime
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
    language_code = Column(String, default='fa')
    subscription_tier = Column(SAEnum(SubscriptionTier), default=SubscriptionTier.FREE)
    subscription_expiry = Column(DateTime(timezone=True), nullable=True)
    reminder_count = Column(Integer, default=0)
    chat_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username='{self.username}')>"

class Reminder(BaseModel):
    __tablename__ = "reminders"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task = Column(String, nullable=False)
    jalali_date_str = Column(String, nullable=True)
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
    def jalali_datetime(self):
        try:
            year, month, day = map(int, self.jalali_date_str.split('-'))
            hour, minute = map(int, self.time_str.split(':'))
            return jdatetime.datetime(year, month, day, hour, minute)
        except ValueError:
            # Handle potential parsing errors
            return None

    @jalali_datetime.setter
    def jalali_datetime(self, dt: jdatetime.datetime):
        self.jalali_date_str = dt.strftime("%Y-%m-%d")
        self.time_str = dt.strftime("%H:%M")

    @property
    def gregorian_datetime(self):
        jd_dt = self.jalali_datetime
        return jd_dt.togregorian() if jd_dt else None 

class Payment(BaseModel):
    __tablename__ = "payments"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    
    track_id = Column(String, unique=True, nullable=False)
    amount = Column(Integer, nullable=False)  # Amount in Rials
    status = Column(Integer, nullable=False)  # See PaymentStatus class in payment.py
    
    ref_id = Column(String, nullable=True)  # Reference ID from payment gateway
    card_number = Column(String, nullable=True)  # Masked card number
    
    response_data = Column(Text, nullable=True)  # Raw JSON response from payment gateway
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User")