#!/usr/bin/env python3
"""
Production bot startup script.
This script ensures the bot runs in a clean environment without event loop conflicts.
"""

import sys
import os
import asyncio
import signal
import logging
from pathlib import Path

# Ensure the src directory is in Python path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}. Shutting down...")
    sys.exit(0)

async def start_bot():
    """Start the bot in a clean async environment."""
    try:
        # Import here to avoid import issues
        from bot import main
        
        logger.info("Starting Telegram reminder bot...")
        await main()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        raise

def main_entry():
    """Main entry point that ensures clean event loop."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Check if we're in an interactive environment
    if hasattr(sys, 'ps1') or hasattr(sys, 'ps2'):
        logger.warning("Detected interactive Python environment.")
        logger.warning("For production use, run this script from a clean shell.")
        return
    
    try:
        # Check if there's already an event loop running
        loop = asyncio.get_running_loop()
        logger.error("An event loop is already running!")
        logger.error("Please run this script from a clean shell environment.")
        logger.error("Exit any Python REPL, Jupyter notebook, or IPython session first.")
        sys.exit(1)
        
    except RuntimeError:
        # No event loop running - this is what we want
        try:
            asyncio.run(start_bot())
        except KeyboardInterrupt:
            logger.info("Bot shutdown completed")
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main_entry() 