from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func
from config import DATABASE_URL

Base = declarative_base()

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False)
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
    print("Database initialized (with recurrence_rule, is_active, and boolean is_sent).")