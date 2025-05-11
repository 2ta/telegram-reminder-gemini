#!/bin/bash

rsync -avz --delete \
  --exclude='.env' \
  --exclude='deploy.sh' \
  /Users/mohammadtootia/projects/telegram_bot_reminder_free/telegram_reminder_bot_project \
  root@45.77.155.59:/home/telegram_reminder_bot_project