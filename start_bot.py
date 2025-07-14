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
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except RuntimeError as e:
        if "Cannot close a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise 