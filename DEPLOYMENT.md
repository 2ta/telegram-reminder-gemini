# 🚀 Deployment Guide

This guide covers automated deployment using GitHub Actions and manual deployment options.

## 📋 Prerequisites

### Server Requirements
- Ubuntu/Debian server with SSH access
- Python 3.8+ installed
- Git installed
- tmux installed
- Root or sudo access

### GitHub Repository Setup
- Repository hosted on GitHub
- SSH access to your server configured

## 🔧 Setup Instructions

### 1. Server Initial Setup

Connect to your server and clone the repository:

```bash
ssh root@45.77.155.59 -p61208
cd /root
git clone https://github.com/2ta/telegram-reminder-gemini.git telegram_reminder_bot_project
cd telegram_reminder_bot_project
```

### 2. Environment Configuration

Create your environment file:

```bash
cp env.sample .env
nano .env
```

Add your configuration:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
GOOGLE_API_KEY=your_google_api_key_here
DATABASE_URL=sqlite:///./default.db
# Add other required variables
```

### 3. GitHub Actions Setup

#### Step 1: Generate SSH Key Pair

On your local machine or server:

```bash
ssh-keygen -t rsa -b 4096 -C "github-actions-deploy"
```

#### Step 2: Add Public Key to Server

Copy the public key to your server:

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub -p 61208 root@45.77.155.59
```

Or manually add it to `~/.ssh/authorized_keys` on the server.

#### Step 3: Add Private Key to GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secret:

| Name | Value |
|------|-------|
| `SSH_PRIVATE_KEY` | Contents of your private key file (`~/.ssh/id_rsa`) |

#### Step 4: Test SSH Connection

Verify the connection works:

```bash
ssh -p 61208 root@45.77.155.59 "echo 'Connection successful'"
```

## 🤖 Automated Deployment (GitHub Actions)

### How It Works

The GitHub Actions workflow (`.github/workflows/deploy.yml`) automatically:

1. **Triggers** on push to `main` branch
2. **Connects** to your server via SSH
3. **Updates** code from GitHub
4. **Installs** dependencies in virtual environment
5. **Restarts** the bot in tmux session
6. **Verifies** deployment success

### Manual Trigger

You can also trigger deployment manually:

1. Go to **Actions** tab in your GitHub repository
2. Select **Deploy Telegram Bot** workflow
3. Click **Run workflow**
4. Choose branch and click **Run workflow**

### Monitoring Deployments

- View deployment logs in the **Actions** tab
- Check deployment status and any errors
- Monitor bot status on the server

## 🛠️ Manual Deployment

### Using the Deployment Script

Run the automated deployment script on your server:

```bash
ssh root@45.77.155.59 -p61208
cd /root/telegram_reminder_bot_project
./scripts/deploy.sh
```

### Manual Step-by-Step

If you prefer manual control:

```bash
# Connect to server
ssh root@45.77.155.59 -p61208

# Navigate to project
cd /root/telegram_reminder_bot_project

# Update code
git pull origin main

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip uninstall -y google-generativeai langchain-google-genai google-ai-generativelanguage || true
pip install -r requirements.txt

# Stop existing bot
tmux kill-session -t telegram_bot 2>/dev/null || true

# Start bot
tmux new-session -d -s telegram_bot
tmux send-keys -t telegram_bot "cd /root/telegram_reminder_bot_project" Enter
tmux send-keys -t telegram_bot "source .venv/bin/activate" Enter
tmux send-keys -t telegram_bot "python start_bot.py" Enter
```

## 📊 Managing the Bot

### View Bot Status

```bash
# List tmux sessions
tmux list-sessions

# Attach to bot session
tmux attach-session -t telegram_bot

# Detach from session (Ctrl+B then D)
```

### Bot Management Commands

```bash
# Stop bot
tmux kill-session -t telegram_bot

# Restart bot (run deployment script)
./scripts/deploy.sh

# View bot logs
tmux capture-pane -t telegram_bot -p

# Check if bot is running
tmux has-session -t telegram_bot && echo "Bot is running" || echo "Bot is not running"
```

### Troubleshooting

#### Bot Not Starting

1. Check tmux session:
   ```bash
   tmux attach-session -t telegram_bot
   ```

2. Check environment variables:
   ```bash
   cat .env
   ```

3. Test imports:
   ```bash
   source .venv/bin/activate
   python -c "from src.bot import main; print('Imports OK')"
   ```

#### Deployment Fails

1. Check SSH connection:
   ```bash
   ssh -p 61208 root@45.77.155.59 "echo 'Connection OK'"
   ```

2. Check GitHub Actions logs in repository

3. Verify server has enough disk space:
   ```bash
   df -h
   ```

#### Dependencies Issues

1. Clear virtual environment:
   ```bash
   rm -rf .venv
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## 🔒 Security Considerations

- Keep your SSH private key secure
- Use GitHub Secrets for sensitive data
- Regularly update server packages
- Monitor deployment logs for any issues
- Consider using a dedicated deployment user instead of root

## 📝 Workflow Customization

You can customize the deployment workflow by editing `.github/workflows/deploy.yml`:

- Change deployment triggers
- Add additional deployment steps
- Modify server paths
- Add notification steps

## 🎯 Quick Commands Reference

```bash
# Deploy manually
./scripts/deploy.sh

# View bot logs
tmux attach-session -t telegram_bot

# Stop bot
tmux kill-session -t telegram_bot

# Check bot status
tmux has-session -t telegram_bot && echo "Running" || echo "Stopped"

# Update and restart (full deployment)
git pull origin main && ./scripts/deploy.sh
``` 