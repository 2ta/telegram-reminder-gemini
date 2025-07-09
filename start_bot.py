#!/usr/bin/env python3
"""
Entrypoint to run only the Telegram bot (no Flask, no threading).
"""
import asyncio
from src.bot import main as bot_main

if __name__ == "__main__":
    asyncio.run(bot_main()) 