# Quick Start Guide - Development Setup (SQLite)

Get your Telegram Reminder Bot running on Render.com (with SQLite) in 5 minutes!

## 🚀 Quick Setup

### 1. Run Setup Script
```bash
python scripts/setup-dev-env.py
```

### 2. Deploy on Render (5 minutes)
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Create new Web Service
3. Connect your GitHub repository
4. Set environment variables (copy from your `.env` file):
   - `TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather`
   - `GEMINI_API_KEY=your_google_api_key`
5. Deploy!

## 📋 Required Environment Variables

Set these in Render dashboard:

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
GEMINI_API_KEY=your_google_api_key
```

## ✅ Test Your Deployment

1. **Health Check:** Visit `https://your-app.onrender.com/health`
2. **Test Bot:** Send message to your Telegram bot
3. **Check Database:** SQLite file will be created automatically in your Render instance

## 🆘 Need Help?

- **Detailed Guide:** See `docs/setup-render-supabase.md`
- **Setup Script:** Run `python scripts/setup-dev-env.py`
- **Issues:** Check Render logs

## 🆓 Free Tier Limits

- **Render:** Sleeps after 15min inactivity
- **Perfect for development and testing!** 