#!/usr/bin/env python3
"""
Bot startup script that delegates to src.bot.main().
This ensures the background reminder job is scheduled.
"""
import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# This file is no longer used for starting the bot.
# Use: python -m telegram.ext -p /root/telegram_reminder_bot_project/bot_entry.py 