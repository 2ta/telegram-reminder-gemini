import unittest
import os

class TestInitialSetup(unittest.TestCase):

    def test_config_loading(self):
        """Test if basic configuration variables can be imported."""
        try:
            from config.config import TELEGRAM_BOT_TOKEN, DATABASE_URL, LOG_LEVEL
            # We don't check for actual values here, just that they can be imported.
            # Actual values depend on the .env file which is not part of the test suite's concern for this basic test.
            self.assertTrue(True, "Successfully imported config variables.") 
        except ImportError as e:
            self.fail(f"Failed to import from config.config: {e}")
        except Exception as e:
            self.fail(f"An unexpected error occurred during config import: {e}")

    def test_logging_setup(self):
        """Test if logging can be set up without errors."""
        try:
            from src.logging_config import setup_logging
            setup_logging() # This will raise an error if config vars for logging are missing/invalid
            # Further tests could involve checking if log files are created or if messages are logged,
            # but for initial setup, just ensuring it runs without error is a good start.
            self.assertTrue(True, "Logging setup ran without throwing an error.")
        except ValueError as e:
             # This can happen if LOG_LEVEL in .env is invalid, or LOG_FILE_PATH is problematic
            self.fail(f"Logging setup failed due to a ValueError (likely bad config): {e}")
        except Exception as e:
            self.fail(f"An unexpected error occurred during logging setup: {e}")

if __name__ == '__main__':
    # This allows running the tests directly from this file
    # However, it's better to run tests using `python -m unittest discover tests` or `pytest`
    
    # For direct execution, ensure .env is loaded if config/config.py relies on it at import time
    # Or, more robustly, ensure tests can run without a .env by providing defaults or mocks.
    
    # For this basic test, we assume that importing config.config will work (even if vars are None)
    # and setup_logging() will use defaults from config.py if .env vars are missing.
    unittest.main() 