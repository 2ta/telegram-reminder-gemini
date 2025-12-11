# Telegram Reminder Bot with Gemini AI

A smart Telegram bot that helps users set reminders using natural language processing powered by Google's Gemini AI.

<!-- Deployment test 2 - Triggering GitHub Actions workflow again -->

## Features

- **Natural Language Understanding**: Create reminders using natural English language
- **Voice Message Support**: Send voice messages to create reminders (supports Persian voice input)
- **Smart Time Parsing**: Understands relative dates like "tomorrow", "next week", "in 2 hours"
- **LangGraph Integration**: Structured conversation flows for complex interactions
- **Payment Integration**: Subscription tiers with Stripe payment gateway
- **Automated Notifications**: Background job system for sending reminder notifications
- **Interactive Reminders**: Snooze and mark-as-done functionality
- **Recurring Reminders**: Support for daily, weekly, and monthly recurring reminders
- **Production Ready**: Systemd service configuration with auto-restart

## 🌐 Language Support

**Important**: This bot is designed to work in English. While voice input supports Persian language for transcription, all user interface elements, commands, and responses are in English to ensure consistency and broader accessibility.

## 🎯 Project Status

✅ **Deployed and Running** - Bot is live and operational at [@ai_reminderbot](https://t.me/ai_reminderbot)

**Current Capabilities**:
- ✅ Creating reminders from text and voice messages
- ✅ Viewing and filtering reminders with pagination
- ✅ Deleting reminders with confirmation
- ✅ Payment integration with Stripe gateway
- ✅ Automated reminder notifications with background jobs
- ✅ Interactive reminder buttons (snooze, mark as done)
- ✅ Recurring reminders (daily, weekly, monthly)
- ✅ Premium user system with tier limits
- ✅ Production deployment with systemd service
- ✅ Comprehensive error handling and logging

**Recently Completed**:
- ✅ Reminder notification system
- ✅ Interactive reminder management
- ✅ Recurring reminder support
- ✅ Premium user logic enforcement

## 🛠 Technology Stack

- **Backend**: Python 3.11+
- **Bot Framework**: python-telegram-bot v20+
- **AI/LLM**: Google Gemini 2.0 Flash
- **Agent Framework**: LangGraph for conversation flows
- **Monitoring**: LangSmith for tracing and debugging
- **Database**: SQLAlchemy with SQLite
- **Speech Recognition**: Google Speech-to-Text API
- **Payments**: Stripe Payment Gateway
- **Deployment**: VPS with systemd service

## 📁 Project Structure

```
telegram_reminder_bot_project/
├── src/                     # Main application source code
│   ├── bot.py              # Telegram bot handlers and logic
│   ├── graph.py            # LangGraph conversation flows
│   ├── graph_nodes.py      # Individual graph nodes and actions
│   ├── graph_state.py      # Conversation state management
│   ├── models.py           # SQLAlchemy database models
│   ├── database.py         # Database utilities and CRUD operations
│   ├── voice_utils.py      # Voice message processing (STT)
│   ├── datetime_utils.py   # Persian/Jalali date parsing utilities
│   └── payment.py          # Stripe payment integration
├── config/                 # Configuration files
│   └── config.py          # Environment variables and settings
├── scripts/               # Deployment and utility scripts
│   ├── deploy.sh         # Automated deployment script
│   ├── setup_admin.py    # Admin user setup
│   ├── setup_payment_domain.sh  # Payment domain setup
│   └── verify_deployment.py     # Deployment verification
├── docs/                 # Project documentation
│   ├── MANAGEMENT.md     # Production management guide
│   ├── FEATURES.md       # Features documentation
│   ├── INTELLIGENT_REMINDER_REFACTORING.md  # AI agent documentation
│   ├── MARKETING_AUTOMATION.md  # Marketing system docs
│   └── specs/           # Technical specifications
├── bot_entry.py         # Main bot entry point
├── app.py               # Combined app for Render.com deployment
├── requirements.txt      # Python dependencies
└── env.sample           # Environment variables template
```

## 🚀 Quick Start

### Local Development

1. **Clone and setup**:
    ```bash
   git clone https://github.com/2ta/telegram-reminder-gemini.git
   cd telegram-reminder-gemini
   python3.11 -m venv .venv
   source .venv/bin/activate
    pip install -r requirements.txt
    ```

2. **Configure environment**:
    ```bash
    cp env.sample .env
   # Edit .env with your API keys and tokens
   ```

3. **Run the bot**:
   ```bash
   python bot_entry.py
   # Or for Render.com deployment:
   python app.py
   ```

### Production Deployment

For production deployment on VPS, see **[Management Guide](docs/MANAGEMENT.md)** for detailed instructions.

Quick production setup:
```bash
# Use the automated deployment script
./scripts/deploy.sh

# Or set up systemd service
sudo systemctl enable telegram-reminder-bot
sudo systemctl start telegram-reminder-bot
```

## 📖 Documentation

- **[Management Guide](docs/MANAGEMENT.md)** - Production deployment and management
- **[Features Documentation](docs/FEATURES.md)** - Complete features list and status
- **[Intelligent Reminder Agent](docs/INTELLIGENT_REMINDER_REFACTORING.md)** - AI-powered reminder system
- **[LangSmith Integration](docs/LANGSMITH_INTEGRATION.md)** - Monitoring and debugging guide
- **[Technical Specifications](docs/specs/spec.md)** - Detailed technical requirements
- **[Marketing Automation](docs/MARKETING_AUTOMATION.md)** - Automated user engagement system

## 🔧 Configuration

### Required Environment Variables

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Google APIs
GOOGLE_API_KEY=your_google_api_key

# LangSmith (Optional - for monitoring and debugging)
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=telegram-reminder-bot

# Payment (Optional)
STRIPE_SECRET_KEY=your_stripe_secret_key
STRIPE_PUBLISHABLE_KEY=your_stripe_publishable_key

# Database (Optional - defaults to SQLite)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
```

### Optional Configuration

See `env.sample` for additional configuration options including logging levels, subscription tiers, and feature flags.

## 🧪 Testing

Run the test suite:
    ```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/

# Run specific test files
python test_admin_mode.py
python test_recurring_reminders.py
```

## 🔍 Monitoring

### Production Monitoring

    ```bash
# Check service status
sudo systemctl status telegram-reminder-bot

# View logs
sudo journalctl -u telegram-reminder-bot -f

# Resource monitoring
htop
```

### Health Checks

The bot includes built-in health monitoring:
- `/ping` command for basic connectivity
- Database connection validation
- API endpoint health checks
- Memory usage tracking

## 🛡 Security

- Environment variables for sensitive data
- Input validation and sanitization
- Rate limiting for API calls
- Secure payment processing with Stripe
- Regular security updates

## 📝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

Please follow the conventional commit format and update documentation as needed.

## 📄 License

This project is licensed under the MIT License. See LICENSE file for details.

## 🤝 Support

- **Issues**: [GitHub Issues](https://github.com/2ta/telegram-reminder-gemini/issues)
- **Documentation**: See `docs/` directory
- **Telegram**: [@ai_reminderbot](https://t.me/ai_reminderbot) (live bot)

## ⭐ Acknowledgments

- Google Gemini AI for natural language understanding
- python-telegram-bot library for Telegram integration
- LangGraph for conversation flow management
- Zibal for payment processing services 