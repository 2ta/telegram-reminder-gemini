#!/usr/bin/env python3
"""
Entry point for the Telegram Reminder Bot.
This script imports and runs the main function from src/bot.py
"""
import sys
import importlib

# Force modules to reload
if 'src.graph_nodes' in sys.modules:
    print("Reloading src.graph_nodes module")
    importlib.reload(sys.modules['src.graph_nodes'])

from src.bot import main

if __name__ == "__main__":
    main()