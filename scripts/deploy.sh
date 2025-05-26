#!/bin/bash

# Telegram Bot Deployment Script
# This script deploys the telegram reminder bot to the server

set -e

echo "🚀 Starting Telegram Bot Deployment..."

# Configuration
PROJECT_DIR="/root/telegram_reminder_bot_project"
TMUX_SESSION="telegram_bot"
PYTHON_CMD="python3"
BOT_SCRIPT="start_bot.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "Project directory $PROJECT_DIR not found!"
    print_status "Please clone the repository first:"
    echo "  git clone https://github.com/2ta/telegram-reminder-gemini.git $PROJECT_DIR"
    exit 1
fi

# Navigate to project directory
cd "$PROJECT_DIR"
print_status "Working in directory: $(pwd)"

# Pull latest changes
print_status "Pulling latest changes from GitHub..."
git pull origin main
print_success "Code updated successfully"

# Set up Python virtual environment
print_status "Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    $PYTHON_CMD -m venv .venv
    print_success "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
source .venv/bin/activate
print_success "Virtual environment activated"

# Upgrade pip
print_status "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
print_status "Installing dependencies..."
# Remove conflicting packages first
pip uninstall -y google-generativeai langchain-google-genai google-ai-generativelanguage 2>/dev/null || true

# Install requirements
pip install -r requirements.txt
print_success "Dependencies installed successfully"

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_warning ".env file not found!"
    if [ -f "env.sample" ]; then
        print_status "Copying env.sample to .env..."
        cp env.sample .env
        print_warning "Please edit .env file with your actual configuration"
    else
        print_error "No env.sample file found. Please create .env file manually."
    fi
fi

# Initialize database
print_status "Setting up database..."
python -c "
import sys
sys.path.append('.')
try:
    from src.database import init_db
    init_db()
    print('Database initialized successfully!')
except Exception as e:
    print(f'Database setup error: {e}')
    # Don't exit on database error, continue deployment
"

# Test imports
print_status "Testing bot imports..."
python -c "
import sys
sys.path.append('.')
try:
    from src.bot import main
    print('Bot imports successful!')
except Exception as e:
    print(f'Import error: {e}')
    exit(1)
"
print_success "Bot imports verified"

# Stop existing bot
print_status "Stopping existing bot..."
tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
print_status "Waiting for graceful shutdown..."
sleep 3

# Start bot in tmux
print_status "Starting bot in tmux session '$TMUX_SESSION'..."
tmux new-session -d -s "$TMUX_SESSION"
tmux send-keys -t "$TMUX_SESSION" "cd $PROJECT_DIR" Enter
tmux send-keys -t "$TMUX_SESSION" "source .venv/bin/activate" Enter
tmux send-keys -t "$TMUX_SESSION" "python $BOT_SCRIPT" Enter

# Wait a moment for bot to start
sleep 5

# Verify deployment
print_status "Verifying deployment..."
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    print_success "Bot tmux session is running"
    
    # Check if bot is actually running
    if tmux capture-pane -t "$TMUX_SESSION" -p | grep -q "Bot started\|Application\|Telegram\|Started"; then
        print_success "Bot appears to be running successfully!"
    else
        print_warning "Bot session exists but may not be running properly"
        print_status "Last few lines from bot session:"
        tmux capture-pane -t "$TMUX_SESSION" -p | tail -5
    fi
    
    print_status "To view bot logs, run: tmux attach-session -t $TMUX_SESSION"
    print_status "To detach from tmux, press: Ctrl+B then D"
else
    print_error "Bot tmux session not found!"
    exit 1
fi

print_success "🎉 Deployment completed successfully!"
print_status "Bot is running in tmux session '$TMUX_SESSION'"

# Show useful commands
echo ""
print_status "Useful commands:"
echo "  View bot logs:    tmux attach-session -t $TMUX_SESSION"
echo "  Stop bot:         tmux kill-session -t $TMUX_SESSION"
echo "  List sessions:    tmux list-sessions"
echo "  Restart bot:      $0"
echo "" 