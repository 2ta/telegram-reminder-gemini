from sqlalchemy import create_engine, Column, DateTime, Table, MetaData, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging
import os
from config import config

settings = config.settings

logger = logging.getLogger(__name__)

# Create engine and session factory
DATABASE_URL = settings.DATABASE_URL
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Check and update database schema if needed
def ensure_db_schema():
    """
    Check for required columns in tables and add them if missing.
    This is a simple migration solution without using alembic.
    """
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # Check reminders table
        if 'reminders' in table_names:
            reminder_columns = [col['name'] for col in inspector.get_columns('reminders')]
            required_reminder_columns = {
                'due_datetime_utc': 'DATETIME',
                'recurrence_rule': 'VARCHAR(100)'
            }
            missing_reminder_cols = {col: dtype for col, dtype in required_reminder_columns.items() 
                                     if col not in reminder_columns}
            if missing_reminder_cols:
                logger.info(f"Missing columns in reminders table: {missing_reminder_cols.keys()}")
                with engine.connect() as conn:
                    for col_name, col_type in missing_reminder_cols.items():
                        logger.info(f"Adding column {col_name} ({col_type}) to reminders table.")
                        sql = text(f"ALTER TABLE reminders ADD COLUMN {col_name} {col_type}")
                        conn.execute(sql)
                    conn.commit()
        else:
            logger.warning("Table 'reminders' not found. Will be created by models.py definition.")

        # Check users table
        if 'users' in table_names:
            user_columns = [col['name'] for col in inspector.get_columns('users')]
            required_user_columns = {
                'chat_id': 'INTEGER',  # Assuming chat_id is an integer
                'is_admin': 'BOOLEAN'  # Admin flag for admin mode features
            }
            missing_user_cols = {col: dtype for col, dtype in required_user_columns.items() 
                                 if col not in user_columns}
            if missing_user_cols:
                logger.info(f"Missing columns in users table: {missing_user_cols.keys()}")
                with engine.connect() as conn:
                    for col_name, col_type in missing_user_cols.items():
                        logger.info(f"Adding column {col_name} ({col_type}) to users table.")
                        if col_type == 'BOOLEAN':
                            # SQLite uses INTEGER for boolean, with default False
                            sql = text(f"ALTER TABLE users ADD COLUMN {col_name} INTEGER DEFAULT 0")
                        else:
                            sql = text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                        conn.execute(sql)
                    conn.commit()
        else:
            logger.warning("Table 'users' not found. Will be created by models.py definition.")

        logger.info("Database schema check/update complete.")
        return True
            
    except Exception as e:
        logger.error(f"Error checking/updating database schema: {e}", exc_info=True)
        return False

# Create tables if they don't exist
def create_db_tables():
    """Create all tables defined by the models"""
    from src.models import Base
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created or updated")

    # Now ensure schema has all required columns
    ensure_db_schema()

# Initialize the database on application startup
def init_db():
    create_db_tables()
    logger.info("Database initialized successfully")

if __name__ == "__main__":
    # This is for initial table creation or migrations (if not using Alembic yet)
    print("Creating database tables...")
    create_db_tables()
    print("Database tables created.") 