#!/usr/bin/env python3
"""
Simple bot startup script that runs the bot module directly.
Use this if start_bot.py has issues.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    # Run the bot module directly
    import asyncio
    from src.bot import main
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Error running bot: {e}")
        sys.exit(1) 