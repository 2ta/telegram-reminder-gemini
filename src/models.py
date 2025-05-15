from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum
import jdatetime

Base = declarative_base()

class SubscriptionTier(enum.Enum):
    FREE = "FREE"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"

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

    reminders = relationship("Reminder", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username='{self.username}')>"

class Reminder(BaseModel):
    __tablename__ = "reminders"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task = Column(String, nullable=False)
    # Store Jalali date as a string for now, will need careful handling for queries
    # Alternatively, store as Gregorian and convert, or store components
    jalali_date_str = Column(String, nullable=False) # e.g., "1403-05-15"
    time_str = Column(String, nullable=False) # e.g., "14:30"
    is_active = Column(Boolean, default=True)
    is_notified = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)

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