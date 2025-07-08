#!/usr/bin/env python3
"""
Combined application for Render.com deployment.
This runs both the Telegram bot and the Stripe webhook server.
"""
import os
import sys
import threading
import time
import logging
from pathlib import Path

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "render_app.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_bot():
    """Run the Telegram bot in a separate thread."""
    try:
        logger.info("Starting Telegram bot...")
        from src.bot import main
        main()
    except Exception as e:
        logger.error(f"Bot thread error: {e}")

def main():
    """Main function to start both services."""
    logger.info("Starting combined application...")
    
    # Ensure required directories exist
    os.makedirs("logs", exist_ok=True)
    os.makedirs("checkpoints", exist_ok=True)
    
    # Start bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Import and run the Flask app (this will be the main thread)
    logger.info("Starting webhook server...")
    from src.payment_callback_server import app
    
    # Run the Flask app (this blocks and runs the web server)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)

if __name__ == "__main__":
    main() 