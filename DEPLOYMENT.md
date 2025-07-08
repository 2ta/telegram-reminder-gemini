# Deployment Guide for Render.com

This guide will help you deploy your Telegram Reminder Bot on Render.com.

## Prerequisites

1. A GitHub account with your bot repository
2. A Render.com account
3. Your Telegram Bot Token from @BotFather
4. Your Google API Key for Gemini
5. Your Stripe API keys

## Step 1: Prepare Your Repository

Ensure your repository contains:
- `app.py` - Combined application for Render
- `render.yaml` - Render deployment configuration
- `runtime.txt` - Python version specification
- `requirements.txt` - Python dependencies
- All your source code in the `src/` directory

## Step 2: Deploy on Render.com

### Option A: Using render.yaml (Recommended)

1. **Connect your GitHub repository:**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New" → "Blueprint"
   - Connect your GitHub account and select your repository
   - Render will automatically detect the `render.yaml` file

2. **Configure environment variables:**
   - In the Render dashboard, go to your service
   - Navigate to "Environment" tab
   - Add the following environment variables:
     ```
     TELEGRAM_BOT_TOKEN=your_telegram_bot_token
     GOOGLE_API_KEY=your_google_api_key
     STRIPE_SECRET_KEY=your_stripe_secret_key
     STRIPE_WEBHOOK_SECRET=your_stripe_webhook_secret
     ```

### Option B: Manual Deployment

1. **Create a new Web Service:**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New" → "Web Service"
   - Connect your GitHub repository

2. **Configure the service:**
   - **Name:** `telegram-reminder-bot`
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
   - **Python Version:** `3.9.18`

3. **Add environment variables** (same as above)

## Step 3: Configure Stripe Webhooks

1. **Get your Render URL:**
   - After deployment, Render will provide a URL like: `https://your-app-name.onrender.com`

2. **Configure Stripe webhook:**
   - Go to [Stripe Dashboard](https://dashboard.stripe.com/webhooks)
   - Click "Add endpoint"
   - **Endpoint URL:** `https://your-app-name.onrender.com/webhook/stripe`
   - **Events to send:** Select all payment-related events
   - Copy the webhook signing secret

3. **Update environment variable:**
   - In Render dashboard, update `STRIPE_WEBHOOK_SECRET` with the signing secret

## Step 4: Test Your Deployment

1. **Check the health endpoint:**
   - Visit: `https://your-app-name.onrender.com/health`
   - Should return: `{"status": "healthy"}`

2. **Test your bot:**
   - Send a message to your Telegram bot
   - Check the logs in Render dashboard

## Step 5: Monitor and Maintain

### Viewing Logs
- Go to your service in Render dashboard
- Click "Logs" tab to view real-time logs

### Environment Variables
- All sensitive data should be stored as environment variables
- Never commit API keys to your repository

### Scaling
- Render automatically scales based on traffic
- Free tier has limitations but is sufficient for testing

## Troubleshooting

### Common Issues

1. **Build fails:**
   - Check that all dependencies are in `requirements.txt`
   - Verify Python version compatibility

2. **Bot not responding:**
   - Check environment variables are set correctly
   - Verify Telegram bot token is valid
   - Check logs for errors

3. **Webhook not working:**
   - Verify Stripe webhook URL is correct
   - Check webhook secret is set correctly
   - Test with Stripe CLI locally first

### Support
- Render Documentation: https://render.com/docs
- Render Community: https://community.render.com

## Security Notes

- Never expose API keys in your code
- Use environment variables for all sensitive data
- Regularly rotate your API keys
- Monitor your Stripe webhook events for security

## Cost Considerations

- **Free Tier:** Limited but sufficient for development/testing
- **Paid Plans:** Start at $7/month for more resources
- **Database:** Consider using Render's PostgreSQL for production

## Next Steps

After successful deployment:
1. Set up monitoring and alerts
2. Configure custom domain (optional)
3. Set up CI/CD for automatic deployments
4. Consider database migration for production use 