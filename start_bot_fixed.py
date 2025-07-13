#!/usr/bin/env python3
"""
Production bot startup script.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import signal
import logging
from src.bot import main as bot_main

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable to handle shutdown
running = True

def signal_handler(signum, frame):
    global running
    logger.info(f'Received signal {signum}. Shutting down...')
    running = False

async def main():
    """Run bot with proper shutdown handling"""
    global running
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info('Starting Telegram reminder bot...')
        await bot_main()
        
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.error(f'Error starting bot: {e}', exc_info=True)
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.error(f'Failed to start bot: {e}')
        sys.exit(1) 