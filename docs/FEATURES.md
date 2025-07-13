# Telegram Reminder Bot - Features Documentation

## Overview
This document tracks all developed features of the Telegram Reminder Bot. It is updated regularly after each new development to maintain a complete record of the bot's capabilities.

**Last Updated:** December 2024  
**Bot Language:** English (All user-facing text is in English)  
**Status:** Production Ready

---

## Core Features

### 1. Reminder Creation System
**Status:** ✅ Implemented  
**Description:** Users can create reminders through text messages or voice input.

**Features:**
- Natural language processing for date/time extraction
- Voice message transcription using Google Speech-to-Text
- Support for various date/time formats
- Automatic timezone handling (UTC)
- Confirmation system before creating reminders

**Technical Details:**
- Uses LangGraph for conversation flow management
- Gemini 2.0 Flash for natural language understanding
- SQLite/PostgreSQL database storage
- Voice processing with temporary file cleanup

### 2. Reminder Notification System
**Status:** ✅ Implemented  
**Description:** Automated background system that sends reminder notifications to users.

**Features:**
- Background job runs every minute to check for due reminders
- Interactive notification buttons (snooze, mark as done)
- Support for recurring reminders (daily, weekly, monthly)
- Automatic status updates in database
- Error handling and retry logic

**Technical Details:**
- Job queue integration with python-telegram-bot
- Inline keyboard buttons for user interaction
- Database status tracking (is_notified, notification_sent_at)
- Recurring reminder calculation and rescheduling

### 3. Premium User System
**Status:** ✅ Implemented  
**Description:** Tiered subscription system with different reminder limits.

**Features:**
- Free tier: 5 active reminders maximum
- Premium tier: 100 active reminders maximum
- Stripe payment integration
- Subscription expiry tracking
- Automatic tier enforcement

**Technical Details:**
- Stripe API integration for payments
- Database subscription tracking
- Payment verification system
- Webhook handling for payment status updates

### 4. Voice Message Processing
**Status:** ✅ Implemented  
**Description:** Convert voice messages to text for reminder creation.

**Features:**
- Google Speech-to-Text API integration
- Persian language support for voice input
- Automatic file cleanup after processing
- Error handling for transcription failures

**Technical Details:**
- Temporary file management
- Audio format conversion
- API error handling and retry logic

### 5. Reminder Management
**Status:** ✅ Implemented  
**Description:** Users can view, filter, and manage their existing reminders.

**Features:**
- List all active reminders with pagination
- Filter reminders by date, status, or keywords
- Delete individual reminders
- Mark reminders as completed
- Snooze functionality for due reminders

**Technical Details:**
- Pagination system (5 reminders per page)
- Database query optimization
- Filter parsing with natural language processing

### 6. Payment Integration
**Status:** ✅ Implemented  
**Description:** Stripe-based payment system for premium subscriptions.

**Features:**
- Secure payment processing
- Payment verification system
- Subscription management
- Webhook handling for payment events

**Technical Details:**
- Stripe API v7+ integration
- Payment status tracking
- Webhook signature verification
- Database payment record management

---

## Technical Architecture

### Backend Stack
- **Language:** Python 3.9+
- **Framework:** python-telegram-bot 20.x
- **AI/ML:** Google Gemini 2.0 Flash, LangGraph
- **Database:** SQLite (development), PostgreSQL (production)
- **Payment:** Stripe API
- **Voice Processing:** Google Speech-to-Text API

### Key Components
1. **LangGraph Application:** Manages conversation flow and state
2. **Database Models:** User, Reminder, Payment entities
3. **Background Jobs:** Reminder notification scheduler
4. **Payment System:** Stripe integration with webhooks
5. **Voice Processing:** Speech-to-text conversion pipeline

### Deployment
- **Platform:** VPS with systemd service
- **Process Management:** systemd service file
- **Logging:** File-based logging with rotation
- **Environment:** Production-ready with environment variables

---

## Language Support

### Current Status
- **Primary Language:** English
- **Voice Input:** Persian (for voice transcription)
- **User Interface:** English only
- **Error Messages:** English
- **Documentation:** English

### Important Note
The bot is designed to work primarily in English. While voice input supports Persian language for transcription, all user-facing text, commands, and responses are in English. This ensures consistency and broader accessibility.

---

## Development History

### Recent Updates (December 2024)
1. **Reminder Notification System:** Added background job scheduler and interactive notifications
2. **Premium User Logic:** Implemented tier-based reminder limits
3. **Payment Integration:** Complete Stripe payment system
4. **Voice Processing:** Persian voice input support
5. **Database Optimization:** Improved query performance and indexing

### Planned Features
- [ ] Multi-language support (UI languages)
- [ ] Advanced recurring reminder patterns
- [ ] Reminder categories/tags
- [ ] Export/import reminder functionality
- [ ] Advanced notification preferences

---

## Configuration

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Bot authentication token
- `DATABASE_URL`: Database connection string
- `STRIPE_SECRET_KEY`: Payment processing key
- `GOOGLE_APPLICATION_CREDENTIALS`: Speech-to-text credentials
- `GEMINI_API_KEY`: AI model access key

### Feature Flags
- `IGNORE_REMINDER_LIMITS`: Development mode flag
- `APP_ENV`: Environment setting (development/testing/production)

---

## Monitoring and Logging

### Log Files
- **Location:** `logs/bot.log`
- **Rotation:** 5MB max size, 3 backup files
- **Level:** Configurable (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### Key Metrics
- Reminder creation success rate
- Notification delivery success rate
- Payment processing success rate
- Voice transcription accuracy
- User engagement metrics

---

## Security Considerations

### Data Protection
- User data stored securely in database
- Payment information handled by Stripe (PCI compliant)
- Voice files deleted immediately after processing
- Environment variables for sensitive configuration

### Access Control
- Telegram user authentication
- Premium feature access control
- Payment verification system
- Webhook signature validation

---

## Performance Optimization

### Database
- Indexed queries for user and reminder lookups
- Efficient pagination for large reminder lists
- Connection pooling for production deployments

### Memory Management
- Garbage collection after AI model invocations
- Temporary file cleanup for voice processing
- Memory usage monitoring and logging

### Background Jobs
- Efficient reminder checking algorithm
- Error handling and retry logic
- Minimal resource usage during idle periods

---

## Troubleshooting

### Common Issues
1. **Voice transcription failures:** Check Google Cloud credentials
2. **Payment processing errors:** Verify Stripe configuration
3. **Database connection issues:** Check DATABASE_URL and permissions
4. **Notification delivery failures:** Verify bot token and permissions

### Debug Mode
Enable debug logging by setting `LOG_LEVEL=DEBUG` in environment variables for detailed troubleshooting information.

---

*This document is automatically updated after each development cycle to maintain accurate feature documentation.* 