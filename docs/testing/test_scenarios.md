# Test Scenarios for Telegram Reminder Bot

## Scenario 1: Simple Reminder with General Time (Without Hour) and Then Specifying Hour
**User:** Remind me to call my brother.
**System:** When do you want me to remind you?
**User:** Tomorrow
**System:** Okay, reminder set.
📝 **Text:** Call my brother
⏰ **Time:** Monday, May 12, 2025, at 9:00 AM.
But if you want a different time, just let me know.
**User:** Remind me at 12 o'clock.
**System:** 12 PM or 12 AM?
**User:** PM
**System:** Okay, reminder set.
📝 **Text:** Call my brother
⏰ **Time:** Monday, May 12, 2025, at 12:00 PM.

---

## Scenario 2: Direct Reminder with Approximate Time and Time Correction
**User:** Remind me to call my brother tomorrow.
**System:** Okay, reminder set.
📝 **Text:** Call my brother
⏰ **Time:** Monday, May 12, 2025, at 9:00 AM.
But if you want a different time, just let me know.
**User:** Remind me at 12 o'clock.
**System:** 12 PM or 12 AM?
**User:** PM
**System:** Okay, reminder set.
📝 **Text:** Call my brother
⏰ **Time:** Monday, May 12, 2025, at 12:00 PM.

---

## Scenario 3: Reminder with Exact Time on the Same Day
**User:** Remind me to text Amir Ali at 10 AM.
**System:** Okay, reminder set.
📝 **Text:** Text Ali
⏰ **Time:** Monday, May 12, 2025, at 10:00 AM.

---

## Scenario 4: Reminder with Specific Date and Time
**User:** Remind me on May 13th at 10 AM to call my dermatologist.
**System:** Okay, reminder set.
📝 **Text:** Call my dermatologist
⏰ **Time:** Tuesday, May 13, 2025, at 10:00 AM.

---

## Scenario 5: Reminder Time Correction by User
**User:** Remind me to buy bread next Monday at 2 PM.
**System:** Reminder for "buy bread" set for Monday, May 12, 2025, at 2:00 PM.
**User:** Change it and remind me on May 13th.
**System:** Okay, updated.
📝 **Text:** Buy bread
⏰ **Time:** May 13, 2025, at 2:00 PM.

---

## Scenario 6: Request for a Re-reminder After Notification
**System:** 🔔 Reminder: Call my brother.
**User:** Remind me again in two hours.
**System:** Okay, reminder updated.
📝 **Text:** Call my brother
⏰ **Time:** May 13, 2025, at 1:00 PM.

---

## Scenario 7: Recurring Reminder (Daily, Weekly, Monthly)
**User:** Remind me every day at 8 PM to take my medications.
**System:** Sure. Daily reminder set.
📝 **Text:** Take medications
⏰ **Time:** Every day at 8:00 PM.

---

## Scenario 8: Relative Reminder Based on Specific Time
**User:** Remind me half an hour before my meeting with Ali to get ready.
**System:** Do you know the time of your meeting with Ali?
**User:** It's at 3 PM.
**System:** Okay, reminder set.
📝 **Text:** Get ready for the meeting with Ali
⏰ **Time:** Today, at 2:30 PM.

---

## Scenario 9: Multi-Stage Reminder
**User:** Remind me to take the clothes to the dry cleaner on Thursday and pick them up on Saturday.
**System:** Okay, two reminders set:
📝 **Text:** Take clothes to the dry cleaner
⏰ **Time:** Thursday, May 15, 2025, at 9:00 AM.
📝 **Text:** Pick up clothes from the dry cleaner
⏰ **Time:** Saturday, May 17, 2025, at 9:00 AM.

---

## Scenario 10: Show Reminders List
**User:** Show me my reminders.
**System:** 📅 Your reminders:
1. Call my brother – Monday, May 12, at 12:00 PM
2. Text a birthday message to Ali – Tuesday, May 13, at 10:00 AM
3. Work out – Every Friday, at 8:00 AM

---

## Scenario 11: Delete One Reminder from List
**User:** Delete number 2.
**System:** 🗑️ Reminder "Text a birthday message to Ali" has been deleted.

---

## Scenario 12: Edit One Reminder from List
**User:** Edit reminder number 1.
**System:** What do you want to change? The text or the time?
**User:** Change the time to 2 PM.
**System:** Okay, it's updated.
📝 **Text:** Call my brother
⏰ **New Time:** Monday, May 12, at 2:00 PM.

---

## Scenario 13: Reminder with Specific Time on the Same Day (Using "Tonight")
**User:** Remind me to call my brother at 11:15 tonight.
**System:** (It should detect today's date and set this reminder if the time has not passed 11:15 PM) Okay, reminder set.
📝 **Text:** Call my brother
⏰ **Time:** Monday, May 12, 2025, at 11:15 PM.