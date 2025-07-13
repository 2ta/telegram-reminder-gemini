#!/bin/bash

# Telegram Reminder Bot Deployment Script
# This script deploys the bot to the production server

set -e

# Configuration
SERVER_HOST="45.77.155.59"
SERVER_PORT="61208"
SERVER_USER="root"
PROJECT_DIR="/root/telegram_reminder_bot_project"
REPO_URL="https://github.com/2ta/telegram-reminder-gemini.git"

echo "🚀 Starting deployment to $SERVER_HOST:$SERVER_PORT..."

# Function to execute commands on remote server
remote_exec() {
    ssh -p $SERVER_PORT $SERVER_USER@$SERVER_HOST "$1"
}

# Function to copy files to remote server
remote_copy() {
    scp -P $SERVER_PORT "$1" $SERVER_USER@$SERVER_HOST:"$2"
}

echo "📥 Checking server connection..."
if ! remote_exec "echo 'Connection test successful'"; then
    echo "❌ Failed to connect to server"
    exit 1
fi

echo "🔧 Setting up project directory..."
remote_exec "
    set -e
    mkdir -p $PROJECT_DIR
    cd $PROJECT_DIR
    
    # Clone or update repository
    if [ ! -d '.git' ]; then
        echo 'Cloning repository...'
        git clone $REPO_URL .
    else
        echo 'Updating repository...'
        git fetch origin
        git reset --hard origin/main
    fi
"

echo "🐍 Setting up Python environment..."
remote_exec "
    set -e
    cd $PROJECT_DIR
    
    # Create virtual environment if it doesn't exist
    if [ ! -d '.venv' ]; then
        python3 -m venv .venv
    fi
    
    # Activate virtual environment and install dependencies
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
"

echo "🗄️ Setting up database..."
remote_exec "
    set -e
    cd $PROJECT_DIR
    source .venv/bin/activate
    
    python -c \"
    import sys
    sys.path.append('.')
    try:
        from src.database import init_db
        init_db()
        print('Database initialized successfully!')
    except Exception as e:
        print(f'Database setup: {e}')
    \"
"

echo "🔧 Setting up systemd service..."
remote_exec "
    set -e
    
    # Create systemd service file
    cat > /etc/systemd/system/telegram-reminder-bot.service << 'SERVICEFILE'
[Unit]
Description=Telegram Reminder Bot with Gemini AI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/start_bot.py
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
SERVICEFILE

    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable telegram-reminder-bot.service
"

echo "🔄 Restarting bot service..."
remote_exec "
    set -e
    
    # Stop existing service
    systemctl stop telegram-reminder-bot.service 2>/dev/null || true
    
    # Wait a moment
    sleep 2
    
    # Start the service
    systemctl start telegram-reminder-bot.service
"

echo "🔍 Verifying deployment..."
remote_exec "
    set -e
    
    # Wait for service to start
    sleep 5
    
    # Check service status
    if systemctl is-active --quiet telegram-reminder-bot.service; then
        echo '✅ Bot service is running'
        
        # Check service logs for any errors
        echo '📋 Recent service logs:'
        journalctl -u telegram-reminder-bot.service --no-pager -n 10
        
        # Check if bot is responding
        echo '🔍 Checking bot process...'
        if pgrep -f 'start_bot.py' > /dev/null; then
            echo '✅ Bot process is running'
        else
            echo '⚠️ Bot process not found, but service is active'
        fi
        
    else
        echo '❌ Bot service is not running'
        echo '📋 Service status:'
        systemctl status telegram-reminder-bot.service --no-pager
        echo '📋 Recent logs:'
        journalctl -u telegram-reminder-bot.service --no-pager -n 20
        exit 1
    fi
"

echo "✅ Deployment completed successfully!"
echo "📊 Bot is now running on the server"
echo "🔗 To check logs: ssh -p $SERVER_PORT $SERVER_USER@$SERVER_HOST 'journalctl -u telegram-reminder-bot.service -f'"
echo "🔗 To restart: ssh -p $SERVER_PORT $SERVER_USER@$SERVER_HOST 'systemctl restart telegram-reminder-bot.service'" 