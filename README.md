# Telegram Reminder Bot with Gemini AI

A smart Telegram bot that uses Google's Gemini AI to understand natural language reminders in Persian (Farsi) and English. The bot can:

- Set reminders with natural language processing
- Handle voice messages through speech-to-text
- Support recurring reminders
- List and manage existing reminders
- Understand date/time in Persian calendar format
- Process premium subscriptions via Zibal payment gateway

## Features

- **Natural Language Understanding**: Uses Google's Gemini AI to extract reminder details from user messages
- **Persian Calendar Support**: Full Jalali (Persian) calendar integration
- **Voice Message Support**: Transcribes voice messages using Google Speech-to-Text
- **Context-Aware Conversations**: Maintains conversation context to improve user experience
- **Recurring Reminders**: Support for daily, weekly, and monthly recurring reminders
- **Premium Subscription**: Integrated payment system using Zibal payment gateway for Iranian users

## Setup

1. Clone the repository
2. Install the requirements: `pip install -r requirements.txt`
3. Create a `.env` file with the following variables:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   GOOGLE_APPLICATION_CREDENTIALS=path_to_your_gcp_credentials.json
   GEMINI_PROJECT_ID=your_gemini_project_id
   GEMINI_LOCATION=your_gemini_location
   GEMINI_MODEL_NAME=gemini-pro
   ZIBAL_MERCHANT_KEY=your_zibal_merchant_key
   TELEGRAM_BOT_URL=https://yourdomain.com/bot
   PAYMENT_AMOUNT=100000  # 10,000 Toman = 100,000 Rial
   ```
4. Run the bot: `python bot.py`

## Usage

Send a message to the bot with a reminder request. For example:
- "Remind me to call mom tomorrow at 5 PM"
- "یادم بنداز فردا ساعت ۵ عصر به مادرم زنگ بزنم"
- "هر روز ساعت ۸ شب یادم بنداز داروهامو بخورم"

### Premium Features

To access premium features, users can use the `/pay` command to initiate a payment through the Zibal payment gateway. After successful payment, their account will be upgraded to premium status for 30 days.

Premium features include:
- Unlimited reminders
- Advanced recurring options
- Priority notification delivery
- Extended reminder history

## Payment Integration

The bot integrates with Zibal, an Iranian payment gateway to process payments in Iranian Rials. The integration includes:

1. Payment request creation with the `/pay` command
2. Secure redirection to the Zibal payment page
3. Webhook handler for payment callbacks
4. Verification of successful payments
5. User status updates after confirmed payment
6. Transaction logging for admin reference

## Deployment

### Manual Deployment

1. Set up your server with Python 3.9+ and pip
2. Clone the repository to your server
3. Create a virtual environment: `python -m venv venv`
4. Activate the virtual environment: `source venv/bin/activate`
5. Install dependencies: `pip install -r requirements.txt`
6. Create a .env file with your credentials
7. Set up a systemd service:
   ```
   # Copy the service file to your user's systemd directory
   cp telegram-reminder-bot.service ~/.config/systemd/user/
   
   # Enable and start the service
   systemctl --user enable telegram-reminder-bot.service
   systemctl --user start telegram-reminder-bot.service
   ```

### Automatic Deployment with GitHub Actions

This repository includes a GitHub Actions workflow for automatic deployment. To use it:

1. Set up your server as described in the manual deployment steps
2. Add the following secrets to your GitHub repository:
   - `SSH_PRIVATE_KEY`: Your private SSH key for connecting to the server
   - `SERVER_IP`: Your server's IP address
   - `SSH_USER`: SSH username for your server
   - `DEPLOY_PATH`: Absolute path to the deployment directory on your server

The workflow will automatically deploy changes when you push to the main branch.

## Requirements

- Python 3.9+
- Telegram bot token
- Google Cloud Platform account with Speech-to-Text and Vertex AI (Gemini) APIs enabled
- Zibal merchant account for payment processing 