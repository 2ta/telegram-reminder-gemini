# Production Bot Startup Guide

## Quick Start (VPS)

### Option 1: Direct Startup (Recommended for testing)
```bash
# 1. Navigate to project directory
cd /root/telegram-reminder-gemini

# 2. Activate virtual environment
source venv/bin/activate

# 3. Start the bot (clean environment)
python start_bot.py
```

### Option 2: Simple Module Runner (Alternative)
```bash
# If start_bot.py has issues, use this simpler approach
cd /root/telegram-reminder-gemini
source venv/bin/activate
python run_bot.py
```

### Option 3: Using the module directly
```bash
# If you get event loop errors, exit any Python REPL first
cd /root/telegram-reminder-gemini
source venv/bin/activate
python -m src.bot
```

### Option 3: Background Process with tmux
```bash
# Start a new tmux session
tmux new-session -d -s telegram-bot

# Attach to the session
tmux attach -t telegram-bot

# Inside tmux, run:
cd /root/telegram-reminder-gemini
source venv/bin/activate
python start_bot.py

# Detach from tmux: Ctrl+B, then D
```

### Option 4: Background Process with screen
```bash
# Start screen session
screen -S telegram-bot

# Inside screen, run:
cd /root/telegram-reminder-gemini
source venv/bin/activate
python start_bot.py

# Detach from screen: Ctrl+A, then D
# Reattach later: screen -r telegram-bot
```

## Troubleshooting

### "RuntimeError: This event loop is already running"
This means you're in a Python REPL or interactive environment:

1. **Exit the Python REPL**: Type `exit()` or press Ctrl+D
2. **Make sure you're in a clean shell**: Run `echo $0` - should show bash/zsh, not python
3. **Use the production startup script**: `python start_bot.py`

### Environment Check
```bash
# Check if you're in Python REPL
python -c "import sys; print('In REPL:' if hasattr(sys, 'ps1') else 'Clean shell')"

# Check running Python processes
ps aux | grep python
```

## Production Deployment (Systemd Service)

For long-term production, create a systemd service:

```bash
# Edit the service file
sudo nano /etc/systemd/system/telegram-reminder-bot.service

# Add the following content:
[Unit]
Description=Telegram Reminder Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram-reminder-gemini
ExecStart=/root/telegram-reminder-gemini/venv/bin/python start_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable and start the service
sudo systemctl enable telegram-reminder-bot
sudo systemctl start telegram-reminder-bot
sudo systemctl status telegram-reminder-bot
```

## Logs and Monitoring

```bash
# View bot logs (if using systemd)
sudo journalctl -u telegram-reminder-bot -f

# View application logs
tail -f logs/bot.log

# Check if bot is responding
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe"
``` 