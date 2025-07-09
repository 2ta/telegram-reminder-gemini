# Deployment Guide (VPS)

This project is now intended for deployment on your own VPS (Virtual Private Server).

## Quick Start

1. Clone the repository to your VPS.
2. Install Python 3.11 and all dependencies:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `env.sample` to `.env` and fill in your secrets.
4. Start the bot:
   ```bash
   python -m src.bot
   ```
5. (Optional) Start the Flask webhook server:
   ```bash
   python -m src.payment_callback_server
   ```

## Notes
- You can use systemd, supervisor, or tmux/screen to keep your processes running.
- For production, use a WSGI server (like gunicorn or uvicorn) for the Flask app.
- Set up your firewall and security as appropriate for your VPS.

---

**All Render.com-specific instructions have been removed.** 