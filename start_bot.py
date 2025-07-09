#!/usr/bin/env python3
"""
Startup script for the Telegram Reminder Bot.
This script ensures only one instance of the bot is running.
"""
import os
import sys
import time
import subprocess
import platform
import logging
from pathlib import Path

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "bot_startup.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def find_bot_processes():
    """Find all running bot processes (excluding this script)."""
    bot_pids = []
    current_pid = os.getpid()
    
    if platform.system() == "Windows":
        try:
            output = subprocess.check_output(["wmic", "process", "where", 
                                           "name='python.exe' OR name='pythonw.exe'", 
                                           "get", "processid,commandline", "/format:csv"]).decode()
            for line in output.strip().split('\n'):
                if "bot_runner.py" in line and str(current_pid) not in line:
                    parts = line.strip().split(',')
                    if len(parts) >= 3:
                        try:
                            pid = int(parts[-1])
                            bot_pids.append(pid)
                        except ValueError:
                            pass
        except Exception as e:
            logger.error(f"Error finding processes on Windows: {e}")
    else:
        try:
            ps_output = subprocess.check_output(["ps", "-e", "-o", "pid,command"]).decode()
            
            for line in ps_output.strip().split('\n'):
                if "python" in line and "bot_runner.py" in line and str(current_pid) not in line:
                    try:
                        pid = int(line.strip().split()[0])
                        bot_pids.append(pid)
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            logger.error(f"Error finding processes on Unix: {e}")

    return bot_pids

def kill_bot_processes():
    """Kill all running bot processes."""
    bot_pids = find_bot_processes()
    if not bot_pids:
        logger.info("No existing bot processes found.")
        return True
    
    logger.info(f"Found {len(bot_pids)} running bot processes. Attempting to terminate them...")
    
    for pid in bot_pids:
        try:
            if platform.system() == "Windows":
                subprocess.call(["taskkill", "/F", "/PID", str(pid)])
            else:
                os.kill(pid, 9)  # SIGKILL
            logger.info(f"Successfully terminated process with PID {pid}")
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
    
    # Verify all processes were killed
    time.sleep(1)
    remaining = find_bot_processes()
    if remaining:
        logger.error(f"Failed to kill {len(remaining)} bot processes: {remaining}")
        return False
    
    return True

def verify_directories():
    """Ensure all necessary directories exist."""
    dirs = ["logs", "checkpoints"]
    for dir_name in dirs:
        os.makedirs(dir_name, exist_ok=True)
        logger.info(f"Verified directory: {dir_name}")

def start_bot():
    """Start the bot process."""
    logger.info("Starting the bot...")
    try:
        # Run the bot in a new process, detached from this script
        if platform.system() == "Windows":
            subprocess.Popen(["python", "bot_runner.py"], 
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            subprocess.Popen(["python", "bot_runner.py"], 
                            start_new_session=True)
        logger.info("Bot started successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to start the bot: {e}")
        return False

def main():
    """Main function."""
    logger.info("Bot startup script initiated.")
    
    # Step 1: Kill any existing bot processes
    if not kill_bot_processes():
        logger.error("Failed to kill all existing bot processes. Please check manually.")
        return
    
    # Step 2: Verify required directories
    verify_directories()
    
    # Step 3: Start the bot
    if start_bot():
        logger.info("Bot startup completed successfully.")
    else:
        logger.error("Bot startup failed.")

if __name__ == "__main__":
    main() 