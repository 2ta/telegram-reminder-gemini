# Test User Payment Reset Script

## Overview
This script allows you to reset payment records for a test user and make them a free tier user. This is useful for testing payment flows without creating multiple test accounts.

## Location
- **Script**: `scripts/reset_test_user_payments.py`
- **Server Path**: `/root/telegram_reminder_bot_project/scripts/reset_test_user_payments.py`

## Usage

### Basic Usage
```bash
# On the server
cd /root/telegram_reminder_bot_project
.venv/bin/python scripts/reset_test_user_payments.py <telegram_id>
```

### Example
```bash
# Reset user with telegram_id 27475074
.venv/bin/python scripts/reset_test_user_payments.py 27475074
```

## What the Script Does

1. **Finds the user** by telegram_id
2. **Deletes all payment records** for that user
3. **Resets subscription tier** to FREE
4. **Clears subscription expiry** date
5. **Resets reminder count** to 0
6. **Logs all actions** for audit trail

## Test User Information
- **Telegram ID**: `27475074`
- **Username**: `mtootia`
- **Purpose**: Payment testing user

## Safety Features
- ✅ **Database transaction**: All changes are wrapped in a transaction
- ✅ **Rollback on error**: If anything fails, all changes are rolled back
- ✅ **Detailed logging**: All actions are logged with timestamps
- ✅ **Validation**: Checks if user exists before proceeding

## Output Example
```
🔄 Resetting payment records for test user 27475074...
📅 Timestamp: 2025-07-27 18:59:50 UTC
--------------------------------------------------
2025-07-27 18:59:50,899 - INFO - Starting payment reset for user 27475074
2025-07-27 18:59:50,945 - INFO - Found user: mtootia (ID: 1)
2025-07-27 18:59:50,946 - INFO - Current subscription tier: PREMIUM
2025-07-27 18:59:50,966 - INFO - Deleting 5 payment records...
2025-07-27 18:59:50,967 - INFO - Resetting subscription tier to FREE
2025-07-27 18:59:51,085 - INFO - ✅ Successfully reset user 27475074 to free tier
✅ Reset completed successfully!
🎯 User is now ready for payment testing
```

## When to Use
- Before testing new payment flows
- After completing payment tests
- When you need a clean slate for payment testing
- Before demonstrating payment features

## Important Notes
- ⚠️ **This script permanently deletes payment records**
- ⚠️ **Only use for test users, never for real customers**
- ⚠️ **Always verify the telegram_id before running**
- ✅ **Safe to run multiple times on the same user**

## Integration with Development Workflow
This script is part of the payment testing workflow:
1. Reset test user → 2. Test payment flow → 3. Verify notifications → 4. Reset again for next test 