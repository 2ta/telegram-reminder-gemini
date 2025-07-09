# Development Setup Guide: Render.com + Supabase

This guide will help you set up your Telegram Reminder Bot for development using Render.com (free tier) and Supabase (free tier).

## Prerequisites

1. **GitHub Account** - Your bot repository should be on GitHub
2. **Render.com Account** - Sign up at [render.com](https://render.com)
3. **Supabase Account** - Sign up at [supabase.com](https://supabase.com)
4. **Telegram Bot Token** - From @BotFather
5. **Google API Key** - For Gemini AI

## Step 1: Set up Supabase Database

### 1.1 Create Supabase Project

1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Click "New Project"
3. Choose your organization
4. Enter project details:
   - **Name:** `telegram-reminder-bot-dev`
   - **Database Password:** Create a strong password (save it!)
   - **Region:** Choose closest to your users
5. Click "Create new project"
6. Wait for setup to complete (2-3 minutes)

### 1.2 Get Database Connection Details

1. In your Supabase project dashboard, go to **Settings** → **Database**
2. Copy the following information:
   - **Host:** `db.[YOUR-PROJECT-REF].supabase.co`
   - **Database name:** `postgres`
   - **Port:** `5432`
   - **User:** `postgres`
   - **Password:** (the one you created)

3. Go to **Settings** → **API**
4. Copy:
   - **Project URL:** `https://[YOUR-PROJECT-REF].supabase.co`
   - **Anon public key**
   - **Service role key** (keep this secret!)

### 1.3 Create Database Tables

Your bot will automatically create the necessary tables when it first runs, but you can also run the database initialization manually:

```bash
# Clone your repository locally
git clone https://github.com/your-username/telegram-reminder-bot.git
cd telegram-reminder-bot

# Create .env file with your Supabase details
cp env.sample .env
# Edit .env with your actual values

# Run database initialization
python -c "from src.database import init_db; init_db()"
```

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
DATABASE_URL=postgresql://postgres:your_password@db.your_project_ref.supabase.co:5432/postgres
SUPABASE_URL=https://your_project_ref.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
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

1. Go to Supabase Dashboard → **Table Editor**
2. You should see tables like `users`, `reminders`, etc.
3. Verify data is being stored correctly

## Step 4: Monitor and Debug

### 4.1 View Logs

- **Render Logs:** Go to your service → "Logs" tab
- **Supabase Logs:** Go to Supabase Dashboard → **Logs**

### 4.2 Common Issues

#### Build Fails
- Check `requirements.txt` has all dependencies
- Verify Python version in `runtime.txt`

#### Bot Not Responding
- Check `TELEGRAM_BOT_TOKEN` is correct
- Verify bot is not blocked by users
- Check Render logs for errors

#### Database Connection Issues
- Verify `DATABASE_URL` format is correct
- Check Supabase project is active
- Ensure IP allowlist includes Render's IPs (if needed)

#### Webhook Issues (if using payments)
- Verify `PAYMENT_CALLBACK_URL_BASE` is correct
- Check Stripe webhook configuration
- Test with Stripe CLI locally first

## Step 5: Development Workflow

### 5.1 Local Development

1. Use local SQLite for development:
   ```bash
   DATABASE_URL=sqlite:///./default.db
   ```

2. Test locally before pushing to GitHub

### 5.2 Deployment Updates

1. Push changes to GitHub
2. Render automatically redeploys
3. Monitor logs for any issues

### 5.3 Database Migrations

For schema changes:
1. Test locally first
2. The bot automatically handles simple schema updates
3. For complex migrations, consider using Alembic

## Free Tier Limitations

### Render.com Free Tier
- **Sleep after inactivity:** 15 minutes
- **Build time:** Limited per month
- **Bandwidth:** Limited
- **No custom domains**

### Supabase Free Tier
- **Database size:** 500MB
- **Bandwidth:** 2GB
- **Auth users:** 50,000
- **API requests:** 50,000 per month

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
- **Supabase Documentation:** https://supabase.com/docs
- **Render Community:** https://community.render.com
- **Supabase Community:** https://github.com/supabase/supabase/discussions 