# Quick Start Guide - VPS Deployment

Get your Telegram Reminder Bot running on your own VPS in minutes!

## 🚀 Quick Setup

### 1. Clone and Install
```bash
git clone <your-repo-url>
cd <your-repo>
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
- Copy `env.sample` to `.env` and fill in your secrets (Telegram token, etc).

### 3. Start the Bot
```bash
python -m src.bot
```

### 4. (Optional) Start the Flask Webhook Server
```bash
python -m src.payment_callback_server
```

## 📝 Notes
- Use `systemd`, `supervisor`, or `tmux`/`screen` to keep your processes running.
- For production, use a WSGI server (like gunicorn or uvicorn) for the Flask app.
- Secure your VPS and keep your secrets safe.

**All Render.com-specific instructions have been removed.** 