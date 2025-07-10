#!/bin/bash

# Payment Domain Setup Script
# This script helps you configure your payment callback domain

echo "🌐 Telegram Bot Payment Domain Setup"
echo "====================================="
echo

# Check if we're on the server
if [[ $(hostname -I) == *"45.77.155.59"* ]]; then
    echo "✅ Running on production server"
    IS_SERVER=true
else
    echo "ℹ️  Running on local machine"
    IS_SERVER=false
fi

echo
echo "📋 Domain Configuration Options:"
echo "1. Use server IP directly (Quick setup)"
echo "2. Use custom domain (Professional setup)"
echo "3. Use localhost (Development only)"
echo

read -p "Choose option (1-3): " option

case $option in
    1)
        if [ "$IS_SERVER" = true ]; then
            DOMAIN="http://45.77.155.59:5000"
        else
            DOMAIN="http://$(curl -s ifconfig.me):5000"
        fi
        echo "✅ Using IP-based domain: $DOMAIN"
        ;;
    2)
        read -p "Enter your domain (e.g., yourdomain.com): " custom_domain
        if [[ $custom_domain == https://* ]]; then
            DOMAIN="$custom_domain"
        elif [[ $custom_domain == http://* ]]; then
            DOMAIN="$custom_domain"
        else
            DOMAIN="https://$custom_domain"
        fi
        echo "✅ Using custom domain: $DOMAIN"
        ;;
    3)
        DOMAIN="http://localhost:5000"
        echo "⚠️  Using localhost (development only): $DOMAIN"
        ;;
    *)
        echo "❌ Invalid option. Exiting."
        exit 1
        ;;
esac

echo
echo "🔧 Updating configuration..."

# Update .env file
if [ -f ".env" ]; then
    # Update existing PAYMENT_CALLBACK_URL_BASE or add it
    if grep -q "PAYMENT_CALLBACK_URL_BASE=" .env; then
        sed -i.bak "s|PAYMENT_CALLBACK_URL_BASE=.*|PAYMENT_CALLBACK_URL_BASE=\"$DOMAIN\"|" .env
        echo "✅ Updated PAYMENT_CALLBACK_URL_BASE in .env"
    else
        echo "" >> .env
        echo "# Payment callback domain" >> .env
        echo "PAYMENT_CALLBACK_URL_BASE=\"$DOMAIN\"" >> .env
        echo "✅ Added PAYMENT_CALLBACK_URL_BASE to .env"
    fi
else
    echo "❌ .env file not found. Creating..."
    echo "PAYMENT_CALLBACK_URL_BASE=\"$DOMAIN\"" > .env
fi

echo
echo "🚀 Setting up payment callback server..."

# Create systemd service for payment callback server
if [ "$IS_SERVER" = true ]; then
    cat > /tmp/telegram-payment-callback.service << EOF
[Unit]
Description=Telegram Bot Payment Callback Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram-reminder-gemini
Environment=PATH=/root/telegram-reminder-gemini/venv/bin
ExecStart=/root/telegram-reminder-gemini/venv/bin/python src/payment_callback_server.py
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegram-payment-callback

[Install]
WantedBy=multi-user.target
EOF

    sudo mv /tmp/telegram-payment-callback.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable telegram-payment-callback
    
    echo "✅ Created systemd service: telegram-payment-callback"
fi

echo
echo "📝 Next steps:"
echo "1. If using custom domain, set up DNS A record pointing to: 45.77.155.59"
echo "2. Start the payment callback server:"

if [ "$IS_SERVER" = true ]; then
    echo "   sudo systemctl start telegram-payment-callback"
    echo "   sudo systemctl status telegram-payment-callback"
else
    echo "   python src/payment_callback_server.py"
fi

echo "3. Test the endpoints:"
echo "   curl $DOMAIN/health"
echo "4. Update your Stripe webhook URL to: $DOMAIN/webhook/stripe"

echo
echo "🎯 Your payment URLs will be:"
echo "   Success: $DOMAIN/payment_success?session_id=..."
echo "   Cancel:  $DOMAIN/payment_cancel"
echo "   Webhook: $DOMAIN/webhook/stripe"

echo
echo "✅ Domain setup complete!" 