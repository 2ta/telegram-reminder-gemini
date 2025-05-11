# Telegram Reminder Bot with Gemini AI

A smart Telegram bot that uses Google's Gemini AI to understand natural language reminders in Persian (Farsi) and English. The bot can:

- Set reminders with natural language processing
- Handle voice messages through speech-to-text
- Support recurring reminders
- List and manage existing reminders
- Understand date/time in Persian calendar format

## Features

- **Natural Language Understanding**: Uses Google's Gemini AI to extract reminder details from user messages
- **Persian Calendar Support**: Full Jalali (Persian) calendar integration
- **Voice Message Support**: Transcribes voice messages using Google Speech-to-Text
- **Context-Aware Conversations**: Maintains conversation context to improve user experience
- **Recurring Reminders**: Support for daily, weekly, and monthly recurring reminders

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
   ```
4. Run the bot: `python bot.py`

## Usage

Send a message to the bot with a reminder request. For example:
- "Remind me to call mom tomorrow at 5 PM"
- "یادم بنداز فردا ساعت ۵ عصر به مادرم زنگ بزنم"
- "هر روز ساعت ۸ شب یادم بنداز داروهامو بخورم"

## Requirements

- Python 3.9+
- Telegram bot token
- Google Cloud Platform account with Speech-to-Text and Vertex AI (Gemini) APIs enabled 