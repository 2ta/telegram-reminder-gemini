"""Version tracking for the telegram reminder bot."""
import subprocess
import datetime
from typing import Optional

def get_git_commit_hash() -> Optional[str]:
    """Get the current git commit hash."""
    try:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()[:8]  # Short hash
    except Exception:
        pass
    return None

def get_git_commit_message() -> Optional[str]:
    """Get the current git commit message."""
    try:
        result = subprocess.run(['git', 'log', '-1', '--pretty=%s'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def get_version_info() -> dict:
    """Get comprehensive version information."""
    commit_hash = get_git_commit_hash()
    commit_message = get_git_commit_message()
    
    return {
        "commit_hash": commit_hash or "unknown",
        "commit_message": commit_message or "unknown",
        "deployment_time": datetime.datetime.now().isoformat(),
        "version": f"v1.0.{commit_hash}" if commit_hash else "v1.0.unknown"
    }

# Constants for easy access
VERSION_INFO = get_version_info()
VERSION = VERSION_INFO["version"]
COMMIT_HASH = VERSION_INFO["commit_hash"] 