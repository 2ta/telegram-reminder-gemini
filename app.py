#!/usr/bin/env python3
"""
Flask-only application for Render.com deployment.
This runs only the Stripe webhook server and health endpoints.
"""
import os
import logging
from pathlib import Path

if __name__ == "__main__":
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

    logger.info("Starting Flask-only application...")
    os.makedirs("logs", exist_ok=True)
    os.makedirs("checkpoints", exist_ok=True)

    from src.payment_callback_server import app

    # Add a root route to avoid 404s
    @app.route("/")
    def index():
        return "Telegram Reminder Bot is running!"

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False) 