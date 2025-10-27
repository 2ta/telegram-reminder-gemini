# Marketing Automation System

## Overview
The Telegram Reminder Bot includes an automated marketing system that sends targeted messages to re-engage users based on their activity patterns. This system helps activate new users and re-engage inactive users.

**Last Updated:** December 2024  
**Status:** ✅ Implemented and Active

---

## Features

### 1. New User Activation (3 Days)
**Purpose:** Re-engage users who registered 3 days ago but haven't created any reminders.

**Trigger Conditions:**
- User registered exactly 3 days ago (±1 hour window)
- User has never created a reminder
- User has not received this marketing message before

**Message Content:**
```
Hi {first_name}! 👋

I noticed you registered with me 3 days ago but haven't created any reminders yet.

💡 Would you like to get started? Here's how I can help:

• Just tell me what you want to be reminded about
• I'll understand natural language ("Remind me to call mom tomorrow at 3pm")
• You can even send voice messages!

🗓️ Try it now:
"Remind me to check my emails every day at 9am"

I'm here to help you stay organized! ✨
```

**Schedule:** Runs every 6 hours (checks 3 days ago within ±1 hour window)

---

### 2. Inactive User Re-engagement (4 Days)
**Purpose:** Re-engage users who previously used the bot but haven't created any reminders in the last 4 days.

**Trigger Conditions:**
- User has created at least one reminder before (has history)
- User hasn't created any reminders in the last 4 days
- User hasn't received this marketing message in the last 4 days

**Message Content:**
```
Hi {first_name}! 👋

I noticed you haven't created any reminders recently. Are you still finding me useful?

🤔 Need help staying organized?

Let me help you get back on track:

💡 Quick Tips:
• "Remind me to exercise every day at 6am"
• "Remind me about the team meeting tomorrow at 2pm"
• "Remind me to take my vitamins daily at 8am"

📱 Just send me a message with what you need, and I'll take care of the rest!

I'm here to help you stay on top of everything! ✨
```

**Schedule:** Runs every 6 hours (checks users inactive for 4+ days)

---

## Technical Implementation

### Database Model
```python
class MarketingMessage(BaseModel):
    __tablename__ = "marketing_messages"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_type = Column(String, nullable=False)  # 'new_user_3days' or 'inactive_4days'
    sent_at = Column(DateTime(timezone=True), nullable=False)
    sent_to_chat_id = Column(Integer, nullable=False)
```

### Background Jobs
- **Location:** `src/bot.py`
- **Jobs:**
  1. `check_and_send_new_user_marketing()` - New user activation
  2. `check_and_send_inactive_user_marketing()` - Inactive user re-engagement
- **Schedule:** Both run every 6 hours
- **First Run:** 1 hour after bot startup

### Job Scheduling
The jobs are scheduled in `build_application()`:
```python
# Schedule marketing automation jobs (runs every 6 hours)
# Convert 6 hours to seconds: 6 * 60 * 60 = 21600
job_queue.run_repeating(check_and_send_new_user_marketing, interval=21600, first=3600)
job_queue.run_repeating(check_and_send_inactive_user_marketing, interval=21600, first=3600)
```

---

## Behavior & Logic

### Message Tracking
- All sent marketing messages are recorded in the `marketing_messages` table
- Prevents duplicate messages from being sent
- Each message type is tracked independently

### Error Handling
- If a message fails to send, it's logged but doesn't stop the job
- Database rollback on individual user failures
- Continues processing other users even if one fails

### Logging
All marketing automation activities are logged:
- Number of users found for targeting
- Message sent confirmations
- Errors and failures
- Duplicate message prevention

---

## Configuration

### Timing Adjustments
To adjust the timing windows, modify:
1. **New user window:** Change `three_days_ago` calculation and window size
2. **Inactive user period:** Change `four_days_ago` time threshold
3. **Job frequency:** Change `interval` parameter in job scheduling

### Message Customization
Edit the message content in:
- `check_and_send_new_user_marketing()` - Line ~1680
- `check_and_send_inactive_user_marketing()` - Line ~1783

---

## Monitoring

### Logs Location
Marketing automation logs appear in: `logs/bot.log`

### Key Log Messages
- `"Checking for new users to send marketing messages..."`
- `"Found X new users without reminders"`
- `"Marketing message sent to user X"`
- `"User X already received new_user_3days marketing message, skipping"`

---

## Future Enhancements
Potential improvements:
1. A/B testing different message variations
2. Adjust timing based on user timezone
3. Send messages at optimal times per user
4. Track conversion rates (messages sent → reminders created)
5. Add more granular targeting (e.g., 7-day, 14-day campaigns)

---

## Testing

### Manual Testing
To test the marketing automation:
1. Create a test user via `/start`
2. Wait for the appropriate period (3 or 4 days)
3. Or manually adjust the database to set `created_at` dates
4. Trigger job manually or wait for scheduled run

### Database Queries
```sql
-- Check sent marketing messages
SELECT * FROM marketing_messages ORDER BY sent_at DESC;

-- Find users who will receive new user message
SELECT u.* FROM users u
WHERE u.created_at BETWEEN datetime('now', '-3 days', '-1 hour') 
  AND datetime('now', '-3 days', '+1 hour')
  AND u.id NOT IN (SELECT DISTINCT user_id FROM reminders);
```

---

## Notes
- Messages are personalized with user's first name
- The system is designed to be non-intrusive and helpful
- Users can opt out by interacting with the bot (creating reminders)
- Marketing messages don't include promotional or sales content
- Focus is on helping users get value from the bot

