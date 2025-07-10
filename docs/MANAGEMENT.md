# Bot Management Guide

This guide covers how to manage the Telegram Reminder Bot in production using the available management scripts and tools.

## Quick Reference

### Management Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| `scripts/deploy.sh` | Root project | Full deployment script with tmux session management |
| `manage_bot.sh` | VPS only | Simple start/stop/status/logs management (server-side) |
| `working_bot.py` | Root project | Production-ready bot script with proper signal handling |

### Essential Commands

```bash
# On VPS - Using systemd service (recommended)
sudo systemctl start telegram-reminder-bot
sudo systemctl stop telegram-reminder-bot  
sudo systemctl status telegram-reminder-bot
sudo systemctl restart telegram-reminder-bot
sudo journalctl -u telegram-reminder-bot -f

# On VPS - Using management script
./manage_bot.sh start
./manage_bot.sh stop
./manage_bot.sh status  
./manage_bot.sh logs

# Local deployment testing
python working_bot.py
```

## Production Deployment

### System Service (Recommended)

The bot is configured as a systemd service for production reliability:

**Service File**: `/etc/systemd/system/telegram-reminder-bot.service`

```ini
[Unit]
Description=Telegram Reminder Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram_reminder_bot_project
Environment=PATH=/root/telegram_reminder_bot_project/.venv/bin
ExecStart=/root/telegram_reminder_bot_project/.venv/bin/python working_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Key Features**:
- Auto-restart on failure
- Starts on boot
- Proper signal handling
- Resource monitoring

### Service Management

```bash
# Enable auto-start on boot
sudo systemctl enable telegram-reminder-bot

# Start/stop service
sudo systemctl start telegram-reminder-bot
sudo systemctl stop telegram-reminder-bot

# Check status and resource usage
sudo systemctl status telegram-reminder-bot

# View real-time logs
sudo journalctl -u telegram-reminder-bot -f

# View recent logs
sudo journalctl -u telegram-reminder-bot --since "1 hour ago"
```

## Development & Testing

### Local Development

For local testing and development:

```bash
# Clone repository
git clone https://github.com/2ta/telegram-reminder-gemini.git
cd telegram-reminder-bot

# Set up virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp env.sample .env
# Edit .env with your tokens and API keys

# Run bot locally
python working_bot.py
```

### Deployment Script

The `scripts/deploy.sh` script automates the entire deployment process:

**Features**:
- Pulls latest code from GitHub
- Sets up virtual environment
- Installs dependencies
- Manages tmux sessions
- Verifies deployment
- Colored output for easy monitoring

**Usage**:
```bash
# Run deployment script
./scripts/deploy.sh

# View tmux session
tmux attach-session -t telegram_bot

# Detach from tmux (Ctrl+B then D)
```

**What it does**:
1. Checks project directory exists
2. Pulls latest changes from `main` branch
3. Sets up/updates Python virtual environment
4. Installs/updates dependencies
5. Checks environment configuration
6. Initializes database if needed
7. Tests bot imports
8. Stops existing tmux session
9. Starts new bot session in tmux
10. Verifies deployment success

## Troubleshooting

### Common Issues

**Bot not responding**:
```bash
# Check service status
sudo systemctl status telegram-reminder-bot

# Check logs for errors
sudo journalctl -u telegram-reminder-bot --since "10 minutes ago"

# Restart service
sudo systemctl restart telegram-reminder-bot
```

**Import errors**:
```bash
# Verify virtual environment
which python
python --version  # Should be 3.11+

# Test imports manually
python -c "from src.bot import main; print('OK')"

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

**Database issues**:
```bash
# Check database file exists
ls -la reminders.db

# Test database connection
python -c "from src.database import init_db; init_db(); print('DB OK')"

# Remove and recreate database (CAUTION: loses data)
rm reminders.db
python -c "from src.database import init_db; init_db()"
```

**Environment configuration**:
```bash
# Check .env file exists and has required variables
cat .env | grep -E "(TELEGRAM_BOT_TOKEN|GOOGLE_API_KEY)"

# Test bot token
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('Token loaded:', bool(os.getenv('TELEGRAM_BOT_TOKEN')))
"
```

### Monitoring

**Resource Usage**:
```bash
# Check memory and CPU usage
sudo systemctl status telegram-reminder-bot

# Detailed process information  
ps aux | grep python | grep -v grep

# System resource monitoring
htop
```

**Log Analysis**:
```bash
# Error patterns
sudo journalctl -u telegram-reminder-bot | grep -i error

# Recent activity
sudo journalctl -u telegram-reminder-bot --since "1 hour ago" | tail -20

# Log file size
du -h logs/
```

### Recovery Procedures

**Complete Reset**:
```bash
# Stop service
sudo systemctl stop telegram-reminder-bot

# Clean environment
rm -rf .venv/
rm -f logs/*

# Redeploy
./scripts/deploy.sh

# Or restart service
sudo systemctl start telegram-reminder-bot
```

**Emergency Manual Start**:
```bash
# If systemd fails, start manually
cd /root/telegram_reminder_bot_project
source .venv/bin/activate
python working_bot.py
```

## Security Notes

- Bot runs as root user (consider creating dedicated user)
- API keys stored in `.env` file (secure file permissions)
- Database file has standard permissions
- Service automatically restarts on failure
- Logs may contain sensitive information

## Performance Monitoring

The bot includes built-in monitoring:
- Message processing times
- Database query performance  
- API call success rates
- Memory usage tracking
- Error rate monitoring

Check logs regularly for performance issues and resource usage patterns.

## Backup & Recovery

**Important files to backup**:
- `reminders.db` - User data and reminders
- `.env` - Configuration and API keys
- `logs/` - Application logs (optional)

**Backup script** (add to cron):
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
cp reminders.db "backups/reminders_$DATE.db"
# Keep only last 7 days
find backups/ -name "reminders_*.db" -mtime +7 -delete
``` 