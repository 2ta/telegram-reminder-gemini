import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import jdatetime

from src.models import Base, User, Reminder, SubscriptionTier
from config.config import settings # To get the test database URL

# Use a separate test database if configured, otherwise use a memory DB for tests
TEST_DATABASE_URL = settings.DATABASE_URL_TEST if settings.DATABASE_URL_TEST else "sqlite:///:memory:"

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session() -> Session:
    Base.metadata.create_all(bind=engine) # Create tables for each test
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine) # Drop tables after each test

def test_create_user(db_session: Session):
    new_user = User(
        telegram_id=12345,
        first_name="Test",
        last_name="User",
        username="testuser",
        language_code="en",
        subscription_tier=SubscriptionTier.FREE
    )
    db_session.add(new_user)
    db_session.commit()
    db_session.refresh(new_user)

    assert new_user.id is not None
    assert new_user.telegram_id == 12345
    assert new_user.first_name == "Test"
    assert new_user.subscription_tier == SubscriptionTier.FREE
    assert new_user.created_at is not None

def test_create_reminder(db_session: Session):
    test_user = User(telegram_id=67890, first_name="ReminderTest")
    db_session.add(test_user)
    db_session.commit()
    db_session.refresh(test_user)

    j_datetime = jdatetime.datetime(1403, 5, 20, 10, 30) # Example Jalali datetime

    new_reminder = Reminder(
        user_id=test_user.id,
        task="Test reminder task",
    )
    new_reminder.jalali_datetime = j_datetime # Use the setter

    db_session.add(new_reminder)
    db_session.commit()
    db_session.refresh(new_reminder)

    assert new_reminder.id is not None
    assert new_reminder.user_id == test_user.id
    assert new_reminder.task == "Test reminder task"
    assert new_reminder.jalali_date_str == "1403-05-20"
    assert new_reminder.time_str == "10:30"
    assert new_reminder.is_active is True
    assert new_reminder.jalali_datetime == j_datetime
    assert new_reminder.gregorian_datetime is not None

def test_user_reminder_relationship(db_session: Session):
    user = User(telegram_id=11122, first_name="RelTest")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    reminder1 = Reminder(user_id=user.id, task="Task 1")
    reminder1.jalali_datetime = jdatetime.datetime(1403, 1, 1, 12, 0)
    reminder2 = Reminder(user_id=user.id, task="Task 2")
    reminder2.jalali_datetime = jdatetime.datetime(1403, 1, 2, 12, 0)

    db_session.add_all([reminder1, reminder2])
    db_session.commit()

    retrieved_user = db_session.query(User).filter(User.id == user.id).first()
    assert retrieved_user is not None
    assert len(retrieved_user.reminders) == 2
    assert retrieved_user.reminders[0].task == "Task 1"
    assert retrieved_user.reminders[1].task == "Task 2" 