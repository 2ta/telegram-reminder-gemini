#!/usr/bin/env python3
"""
Bot startup script that delegates to src.bot.main().
This ensures the background reminder job is scheduled.
"""
import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.bot import main

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Bot stopped by user')
        sys.exit(0)
    except Exception as e:
        print(f'Failed to start bot: {e}')
        sys.exit(1) 