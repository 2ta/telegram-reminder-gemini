from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger, Boolean, Float, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
from config import DATABASE_URL

Base = declarative_base()

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_db_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False)
    task_description = Column(String, nullable=False)
    due_datetime_utc = Column(DateTime(timezone=True), nullable=False)
    
    recurrence_rule = Column(String, nullable=True) # e.g., "daily", "weekly_monday@09:00", "every friday"
    is_active = Column(Boolean, default=True, nullable=False) # For soft deletes / completed / paused
    
    # is_sent is useful for non-recurring reminders to ensure they are sent only once
    # if the bot restarts before is_active is set to False.
    is_sent = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # last_interacted_with = Column(DateTime(timezone=True), nullable=True) # For future "modify last one"

    user = relationship("User")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    language_code = Column(String, nullable=True)
    
    is_premium = Column(Boolean, default=False, nullable=False)
    premium_until = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    payments = relationship("Payment", back_populates="user")
    reminders = relationship("Reminder", back_populates="user")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    
    track_id = Column(String, unique=True, nullable=False)
    amount = Column(Integer, nullable=False)  # Amount in Rials
    status = Column(Integer, nullable=False)  # See PaymentStatus class in payment.py
    
    ref_id = Column(String, nullable=True)  # Reference ID from payment gateway
    card_number = Column(String, nullable=True)  # Masked card number
    
    response_data = Column(Text, nullable=True)  # Raw JSON response from payment gateway
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="payments")

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized (with User and Payment models added).")