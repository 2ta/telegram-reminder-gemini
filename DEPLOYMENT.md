# Deployment Guide

This guide explains how to deploy the Telegram Reminder Bot to your server using GitHub Actions or manual deployment.

## 🚀 Automatic Deployment (GitHub Actions)

### Prerequisites

1. **SSH Key Setup**
   - Generate an SSH key pair if you don't have one:
     ```bash
     ssh-keygen -t rsa -b 4096 -C "your-email@example.com"
     ```
   - Add the **public key** to your server:
     ```bash
     ssh-copy-id -p 61208 root@45.77.155.59
     ```
   - Add the **private key** to GitHub Secrets:
     - Go to your GitHub repository
     - Navigate to Settings → Secrets and variables → Actions
     - Create a new secret named `SSH_PRIVATE_KEY`
     - Paste the content of your private key file (usually `~/.ssh/id_rsa`)

2. **Server Access**
   - Ensure you have SSH access to your server: `ssh root@45.77.155.59 -p61208`
   - The server should have Python 3.9+ installed

### Deployment Process

1. **Push to Main Branch**
   - Any push to the `main` branch will trigger automatic deployment
   - You can also manually trigger deployment from GitHub Actions tab

2. **Monitor Deployment**
   - Go to your GitHub repository → Actions tab
   - Click on the latest workflow run to see deployment progress
   - Check the logs for any errors

## 🔧 Manual Deployment

### Using the Deployment Script

1. **Run the deployment script:**
   ```bash
   ./scripts/deploy.sh
   ```

2. **The script will:**
   - Connect to your server
   - Clone/update the repository
   - Set up Python virtual environment
   - Install dependencies
   - Initialize database
   - Create systemd service
   - Start the bot service

### Manual Server Setup

If you prefer to set up manually:

1. **Connect to your server:**
   ```bash
   ssh root@45.77.155.59 -p61208
   ```

2. **Clone the repository:**
   ```bash
   cd /root
   git clone https://github.com/2ta/telegram-reminder-gemini.git telegram_reminder_bot_project
   cd telegram_reminder_bot_project
   ```

3. **Set up Python environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp env.sample .env
   # Edit .env with your actual configuration
   nano .env
   ```

5. **Initialize database:**
   ```bash
   python -c "
   import sys
   sys.path.append('.')
   from src.database import init_db
   init_db()
   "
   ```

6. **Create systemd service:**
   ```bash
   sudo tee /etc/systemd/system/telegram-reminder-bot.service > /dev/null << 'EOF'
   [Unit]
   Description=Telegram Reminder Bot with Gemini AI
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/root/telegram_reminder_bot_project
   ExecStart=/root/telegram_reminder_bot_project/.venv/bin/python /root/telegram_reminder_bot_project/start_bot.py
   Restart=on-failure
   RestartSec=10
   StartLimitBurst=3
   StartLimitInterval=60

   # Memory Management
   MemoryHigh=500M
   MemoryMax=800M
   MemorySwapMax=0

   # Environment
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   EOF
   ```

7. **Enable and start the service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable telegram-reminder-bot.service
   sudo systemctl start telegram-reminder-bot.service
   ```

## 📊 Monitoring and Management

### Check Bot Status
```bash
# Check if service is running
sudo systemctl status telegram-reminder-bot.service

# View real-time logs
sudo journalctl -u telegram-reminder-bot.service -f

# View recent logs
sudo journalctl -u telegram-reminder-bot.service --no-pager -n 50
```

### Bot Management Commands
```bash
# Restart the bot
sudo systemctl restart telegram-reminder-bot.service

# Stop the bot
sudo systemctl stop telegram-reminder-bot.service

# Start the bot
sudo systemctl start telegram-reminder-bot.service

# Check if bot process is running
pgrep -f start_bot.py
```

### Update Bot
```bash
# Pull latest changes
cd /root/telegram_reminder_bot_project
git pull origin main

# Install new dependencies (if any)
source .venv/bin/activate
pip install -r requirements.txt

# Restart the service
sudo systemctl restart telegram-reminder-bot.service
```

## 🔐 Environment Variables

Make sure to set up these environment variables in your `.env` file:

### Required
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token from BotFather
- `GEMINI_API_KEY` - Your Google Gemini API key

### Optional
- `DATABASE_URL` - Database connection string (defaults to SQLite)
- `STRIPE_SECRET_KEY` - For payment functionality
- `STRIPE_PUBLISHABLE_KEY` - For payment functionality
- `PAYMENT_CALLBACK_URL_BASE` - For payment webhooks

## 🐛 Troubleshooting

### Common Issues

1. **Service won't start:**
   ```bash
   # Check service status
   sudo systemctl status telegram-reminder-bot.service
   
   # Check logs
   sudo journalctl -u telegram-reminder-bot.service --no-pager -n 20
   ```

2. **Permission issues:**
   ```bash
   # Ensure proper ownership
   sudo chown -R root:root /root/telegram_reminder_bot_project
   ```

3. **Python dependencies:**
   ```bash
   # Reinstall dependencies
   cd /root/telegram_reminder_bot_project
   source .venv/bin/activate
   pip install -r requirements.txt --force-reinstall
   ```

4. **Database issues:**
   ```bash
   # Reinitialize database
   cd /root/telegram_reminder_bot_project
   source .venv/bin/activate
   python -c "
   import sys
   sys.path.append('.')
   from src.database import init_db
   init_db()
   "
   ```

### Getting Help

- Check the logs: `sudo journalctl -u telegram-reminder-bot.service -f`
- Verify environment variables are set correctly
- Ensure all required API keys are valid
- Check network connectivity for external API calls

## 🔄 Continuous Deployment

With GitHub Actions set up, every push to the `main` branch will automatically:

1. Deploy to your server
2. Update the code
3. Install new dependencies
4. Restart the bot service
5. Verify the deployment

This ensures your bot is always running the latest version with minimal downtime. 