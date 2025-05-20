#!/usr/bin/env python3
"""
Utility script to find and kill conflicting Telegram bot processes.
The error 'terminated by other getUpdates request' often happens when
multiple instances of the bot are running and trying to use the same bot token.
"""
import os
import sys
import signal
import subprocess
import platform
import time

def find_bot_processes():
    """
    Find all Python processes related to the bot.
    Returns a list of PIDs (process IDs).
    """
    bot_pids = []
    
    if platform.system() == "Windows":
        # For Windows
        try:
            output = subprocess.check_output(["wmic", "process", "where", 
                                           "name='python.exe' OR name='pythonw.exe'", 
                                           "get", "processid,commandline", "/format:csv"]).decode()
            for line in output.strip().split('\n'):
                if "bot_runner.py" in line:
                    parts = line.strip().split(',')
                    if len(parts) >= 3:  # Basic validation
                        try:
                            pid = int(parts[-1])
                            bot_pids.append(pid)
                        except ValueError:
                            pass
        except Exception as e:
            print(f"Error finding processes on Windows: {e}")
    else:
        # For Unix-like systems (Linux, macOS)
        try:
            # Find all Python processes
            ps_output = subprocess.check_output(["ps", "-e", "-o", "pid,command"]).decode()
            
            for line in ps_output.strip().split('\n'):
                # Check if this is a bot_runner.py process
                if "python" in line and "bot_runner.py" in line:
                    try:
                        pid = int(line.strip().split()[0])
                        bot_pids.append(pid)
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            print(f"Error finding processes on Unix: {e}")

    return bot_pids

def kill_process(pid, force=False):
    """
    Kill a process by PID.
    If force is True, use SIGKILL instead of SIGTERM.
    Returns True if successful, False otherwise.
    """
    try:
        if platform.system() == "Windows":
            subprocess.call(["taskkill", "/F" if force else "", "/PID", str(pid)])
        else:
            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        print(f"Successfully terminated process with PID {pid}")
        return True
    except Exception as e:
        print(f"Failed to kill process {pid}: {e}")
        return False

def main():
    """
    Main function to find and kill bot processes.
    """
    # Get the PID of the current process to exclude it
    current_pid = os.getpid()
    
    # Find bot processes
    bot_pids = find_bot_processes()
    
    # Remove current process from the list if it's there
    if current_pid in bot_pids:
        bot_pids.remove(current_pid)
    
    if not bot_pids:
        print("No other bot processes found.")
        return
    
    print(f"Found {len(bot_pids)} bot processes:")
    for pid in bot_pids:
        print(f"  - PID: {pid}")
    
    confirm = input("Do you want to terminate these processes? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation canceled.")
        return
    
    # Kill the processes
    for pid in bot_pids:
        kill_process(pid)
        # Give a short delay to allow the process to terminate
        time.sleep(0.5)
    
    # Check if any processes still exist
    remaining_pids = [pid for pid in bot_pids if pid in find_bot_processes()]
    if remaining_pids:
        print(f"\n{len(remaining_pids)} processes still running after termination attempt.")
        force_confirm = input("Do you want to force kill these processes? (y/n): ")
        if force_confirm.lower() == 'y':
            for pid in remaining_pids:
                kill_process(pid, force=True)
    
    print("\nOperation completed.")

if __name__ == "__main__":
    main() 