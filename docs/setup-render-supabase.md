# Development Setup Guide: Render.com (SQLite Only)

This guide will help you set up your Telegram Reminder Bot for development using Render.com (free tier) with SQLite as the database.

## Prerequisites

1. **GitHub Account** - Your bot repository should be on GitHub
2. **Render.com Account** - Sign up at [render.com](https://render.com)
3. **Telegram Bot Token** - From @BotFather
4. **Google API Key** - For Gemini AI

## Step 1: Prepare Your Repository

- Ensure your repository contains:
  - `app.py` - Combined application for Render
  - `runtime.txt` - Python version specification
  - `requirements.txt` - Python dependencies (no PostgreSQL/psycopg2)
  - All your source code in the `src/` directory
  - `render.yaml` for Render.com configuration

## Step 2: Deploy on Render.com

### 2.1 Connect Repository

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub account if not already connected
4. Select your bot repository

### 2.2 Configure Service

Fill in the service configuration:

- **Name:** `telegram-reminder-bot-dev`
- **Environment:** `Python`
- **Region:** Choose closest to your users
- **Branch:** `main`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python app.py`
- **Plan:** `Free`

### 2.3 Add Environment Variables

Click "Advanced" and add these environment variables:

#### Required Variables:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GEMINI_API_KEY=your_google_api_key_here
```

#### Optional Variables (if using payments):
```
STRIPE_SECRET_KEY=your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=your_stripe_webhook_secret
PAYMENT_CALLBACK_URL_BASE=https://your-app-name.onrender.com/api
```

#### Development Variables (already set in render.yaml):
```
APP_ENV=development
LOG_LEVEL=INFO
DEFAULT_LANGUAGE=fa
IGNORE_REMINDER_LIMITS=True
PORT=5000
```

### 2.4 Deploy

1. Click "Create Web Service"
2. Wait for build to complete (2-5 minutes)
3. Your app will be available at: `https://your-app-name.onrender.com`

## Step 3: Test Your Deployment

### 3.1 Health Check

Visit your app URL + `/health`:
```
https://your-app-name.onrender.com/health
```

Should return: `{"status": "healthy"}`

### 3.2 Test Bot

1. Send a message to your Telegram bot
2. Check if it responds
3. Check Render logs for any errors

### 3.3 Check Database

- SQLite database file will be created in your Render.com instance (e.g., `default.db`)
- You can download logs or database files from the Render dashboard if needed

## Step 4: Monitor and Debug

### 4.1 View Logs

- **Render Logs:** Go to your service → "Logs" tab

### 4.2 Common Issues

#### Build Fails
- Check `requirements.txt` has all dependencies
- Verify Python version in `runtime.txt`

#### Bot Not Responding
- Check `TELEGRAM_BOT_TOKEN` is correct
- Verify bot is not blocked by users
- Check Render logs for errors

#### Webhook Issues (if using payments)
- Verify `PAYMENT_CALLBACK_URL_BASE` is correct
- Check Stripe webhook configuration
- Test with Stripe CLI locally first

## Free Tier Limitations

### Render.com Free Tier
- **Sleep after inactivity:** 15 minutes
- **Build time:** Limited per month
- **Bandwidth:** Limited
- **No custom domains**

## Security Best Practices

1. **Never commit secrets** to your repository
2. **Use environment variables** for all sensitive data
3. **Rotate API keys** regularly
4. **Monitor usage** to stay within free tier limits
5. **Backup important data** regularly

## Next Steps

After successful development setup:

1. **Set up monitoring** and alerts
2. **Configure CI/CD** for automatic deployments
3. **Set up staging environment** for testing
4. **Plan production migration** when ready
5. **Consider paid plans** for higher limits

## Support Resources

- **Render Documentation:** https://render.com/docs
- **Render Community:** https://community.render.com 