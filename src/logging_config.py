import logging
import sys
from logging.handlers import RotatingFileHandler
from config.config import LOG_LEVEL, LOG_FILE_PATH, LOG_FILE_MAX_BYTES, LOG_FILE_BACKUP_COUNT

def setup_logging():
    """Configures logging for the application."""
    numeric_level = getattr(logging, LOG_LEVEL.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {LOG_LEVEL}')

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level)

    # Define a standard log format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Rotating File Handler
    # Ensure logs directory exists (it should, but good practice to check)
    import os
    os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
    
    file_handler = RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info("Logging configured: Level=%s, Path=%s", LOG_LEVEL, LOG_FILE_PATH)

if __name__ == '__main__':
    # Example of using the logger after setup
    setup_logging()
    logging.getLogger(__name__).info("This is an info message from logging_config.py direct run.")
    logging.getLogger(__name__).debug("This is a debug message - should not appear if LOG_LEVEL=INFO.")
    try:
        1 / 0
    except ZeroDivisionError:
        logging.getLogger(__name__).error("This is an error message with exception info.", exc_info=True) 