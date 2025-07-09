# Quick Start Guide - Development Setup

Get your Telegram Reminder Bot running on Render.com + Supabase in 10 minutes!

## 🚀 Quick Setup

### 1. Run Setup Script
```bash
python scripts/setup-dev-env.py
```

### 2. Set up Supabase (5 minutes)
1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Create new project: `telegram-reminder-bot-dev`
3. Copy database connection details
4. Update your `.env` file with:
   ```
   DATABASE_URL=postgresql://postgres:your_password@db.your_project_ref.supabase.co:5432/postgres
   SUPABASE_URL=https://your_project_ref.supabase.co
   SUPABASE_ANON_KEY=your_anon_key
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   ```

### 3. Deploy on Render (5 minutes)
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Create new Web Service
3. Connect your GitHub repository
4. Set environment variables (copy from your `.env` file)
5. Deploy!

## 📋 Required Environment Variables

Set these in Render dashboard:

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
DATABASE_URL=postgresql://postgres:password@db.project_ref.supabase.co:5432/postgres
SUPABASE_URL=https://project_ref.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
GEMINI_API_KEY=your_google_api_key
```

## ✅ Test Your Deployment

1. **Health Check:** Visit `https://your-app.onrender.com/health`
2. **Test Bot:** Send message to your Telegram bot
3. **Check Database:** Go to Supabase → Table Editor

## 🆘 Need Help?

- **Detailed Guide:** See `docs/setup-render-supabase.md`
- **Setup Script:** Run `python scripts/setup-dev-env.py`
- **Issues:** Check Render logs and Supabase logs

## 🆓 Free Tier Limits

- **Render:** Sleeps after 15min inactivity
- **Supabase:** 500MB database, 50K API requests/month
- **Perfect for development and testing!** 