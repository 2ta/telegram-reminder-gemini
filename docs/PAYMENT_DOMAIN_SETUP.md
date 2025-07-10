# Payment Domain Setup Guide

## 🎯 Quick Setup (Recommended)

### Option 1: Use Server IP (Immediate Setup)

1. **Update .env on server:**
   ```bash
   ssh root@45.77.155.59 -p61208
   cd telegram-reminder-gemini
   ```

2. **Edit .env file:**
   ```bash
   nano .env
   ```

3. **Update/add this line:**
   ```
   PAYMENT_CALLBACK_URL_BASE="http://45.77.155.59:5000"
   ```

4. **Start payment callback server:**
   ```bash
   # Install Flask if not already installed
   source venv/bin/activate
   pip install flask
   
   # Start the callback server in background
   nohup python src/payment_callback_server.py > logs/payment_callback.log 2>&1 &
   ```

5. **Restart the bot:**
   ```bash
   systemctl restart telegram-reminder-bot
   ```

### Option 2: Use Custom Domain (Professional Setup)

1. **Set up DNS A record:**
   - Point your domain to: `45.77.155.59`
   - Example: `api.yourdomain.com → 45.77.155.59`

2. **Update .env:**
   ```
   PAYMENT_CALLBACK_URL_BASE="https://api.yourdomain.com"
   ```

3. **Set up SSL (recommended):**
   ```bash
   # Install certbot
   apt install certbot
   
   # Get SSL certificate
   certbot certonly --standalone -d api.yourdomain.com
   ```

4. **Update payment server for HTTPS:**
   - Modify `src/payment_callback_server.py` to use SSL certificates

## 🧪 Testing Your Setup

### 1. Test Health Endpoint
```bash
curl http://45.77.155.59:5000/health
# Should return: {"status":"healthy"}
```

### 2. Test Payment Flow
1. Click "Upgrade to Premium" in bot
2. Complete Stripe test payment
3. Check redirect URL matches your domain
4. Verify in logs: `tail -f logs/payment_callback.log`

### 3. Check Payment Success
```bash
# Your redirect should be:
http://45.77.155.59:5000/payment_success?session_id=cs_test_...
```

## 🔧 Production Configuration

### Webhook Configuration (For Automatic Payment Updates)

1. **In Stripe Dashboard:**
   - Go to Developers → Webhooks
   - Add endpoint: `http://45.77.155.59:5000/webhook/stripe`
   - Select events: `checkout.session.completed`

2. **Update webhook secret in .env:**
   ```
   STRIPE_WEBHOOK_SECRET="whsec_your_real_webhook_secret"
   ```

### Service Management

```bash
# Check if payment server is running
ps aux | grep payment_callback_server

# View logs
tail -f logs/payment_callback.log

# Restart if needed
pkill -f payment_callback_server
nohup python src/payment_callback_server.py > logs/payment_callback.log 2>&1 &
```

## 🌐 URL Structure

After setup, your payment URLs will be:

- **Success**: `http://45.77.155.59:5000/payment_success?session_id=...`
- **Cancel**: `http://45.77.155.59:5000/payment_cancel`
- **Webhook**: `http://45.77.155.59:5000/webhook/stripe`
- **Health**: `http://45.77.155.59:5000/health`

## ⚠️ Security Notes

- For production, use HTTPS instead of HTTP
- Set up proper firewall rules for port 5000
- Use environment variables for sensitive data
- Consider using a reverse proxy (nginx) for better security

## 🚨 Troubleshooting

### Payment Server Not Starting
```bash
# Check if port 5000 is available
netstat -tlnp | grep :5000

# Check for Python/Flask errors
python src/payment_callback_server.py
```

### Payments Not Completing
1. Check bot logs: `tail -f logs/bot.log`
2. Check payment server logs: `tail -f logs/payment_callback.log`
3. Verify .env configuration
4. Test with `curl http://45.77.155.59:5000/health`

### Domain Not Accessible
1. Verify DNS propagation: `nslookup yourdomain.com`
2. Check firewall settings: `ufw status`
3. Verify server is listening: `netstat -tlnp | grep :5000` 