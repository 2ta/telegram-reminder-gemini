import logging
import re
from datetime import datetime, timedelta, timezone, time
from typing import Optional, Tuple, Dict
import pytz

logger = logging.getLogger(__name__)

# English time mappings
ENGLISH_TIME_PERIODS = {
    "morning": time(9, 0),     # 9:00 AM
    "noon": time(12, 30),      # 12:30 PM
    "afternoon": time(15, 0),  # 3:00 PM
    "evening": time(17, 0),    # 5:00 PM
    "dusk": time(18, 30),      # 6:30 PM
    "night": time(21, 0),      # 9:00 PM
    "midnight": time(0, 0),    # Midnight
}

# English weekday mappings
ENGLISH_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# English month mappings
ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12
}

def get_current_utc_time() -> datetime:
    """Returns current UTC datetime."""
    return datetime.now(timezone.utc)

def parse_english_datetime_to_utc(date_str: Optional[str], time_str: Optional[str], user_timezone: str = 'UTC') -> Optional[datetime]:
    """
    Parses English date and time strings into a UTC datetime object.
    Example date_str: "tomorrow", "next week", "monday", "january 15", "2024/1/15"
    Example time_str: "9 am", "evening", "in 30 minutes", "10:30"
    """
    now_utc = get_current_utc_time()
    target_date: Optional[datetime.date] = None
    target_time: Optional[datetime.time] = None

    # 1. Parse Date String
    if date_str:
        date_str_cleaned = date_str.strip().lower()
        
        if date_str_cleaned == "today":
            target_date = now_utc.date()
        elif date_str_cleaned == "tomorrow":
            target_date = (now_utc + timedelta(days=1)).date()
        elif date_str_cleaned == "day after tomorrow":
            target_date = (now_utc + timedelta(days=2)).date()
        else:
            # Relative days/weeks/months: "X days/weeks/months from now"
            m_relative = re.match(r"(\d+)\s+(day|week|month)s?\s+(from now|later|ahead)", date_str_cleaned)
            if m_relative:
                value = int(m_relative.group(1))
                unit = m_relative.group(2)
                if unit == "day":
                    target_date = (now_utc + timedelta(days=value)).date()
                elif unit == "week":
                    target_date = (now_utc + timedelta(weeks=value)).date()
                elif unit == "month":
                    # Approximate: 30 days per month
                    target_date = (now_utc + timedelta(days=value * 30)).date()
            
            if not target_date:
                # Specific dates: YYYY/MM/DD or YYYY-MM-DD
                m_specific = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", date_str_cleaned)
                if m_specific:
                    try:
                        year, month, day = int(m_specific.group(1)), int(m_specific.group(2)), int(m_specific.group(3))
                        target_date = datetime.date(year, month, day)
                    except ValueError as e:
                        logger.warning(f"Invalid date components from regex: {date_str_cleaned} - {e}")
            
            if not target_date:
                # Weekdays: "monday", "next monday"
                for name, day_index in ENGLISH_WEEKDAYS.items():
                    if name in date_str_cleaned:
                        days_ahead = (day_index - now_utc.weekday() + 7) % 7
                        if days_ahead == 0:  # If it's today, make it next week unless specified "today"
                            if "today" not in date_str_cleaned:
                                days_ahead = 7
                        target_date = (now_utc + timedelta(days=days_ahead)).date()
                        break
            
            if not target_date:
                # Dates like "14 July", "July 14", "15th january", "january 15th", "22 July 2025"
                # Updated regex to handle optional year
                m_day_month_year = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)(?:\s+(\d{4}))?", date_str_cleaned)
                if m_day_month_year:
                    day_str = m_day_month_year.group(1)
                    month_name_str = m_day_month_year.group(2)
                    year_str = m_day_month_year.group(3)
                    try:
                        day = int(day_str)
                        month = ENGLISH_MONTHS.get(month_name_str.lower())
                        year = int(year_str) if year_str else now_utc.year
                        if month and 1 <= day <= 31:
                            target_date = datetime.date(year, month, day)
                            # If no year was provided and the date is in the past, assume next year
                            if not year_str and target_date < now_utc.date():
                                target_date = datetime.date(now_utc.year + 1, month, day)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse day/month/year from '{date_str_cleaned}': {e}")
                
                # Second try: "July 14 2025" format
                if not target_date:
                    m_month_day_year = re.match(r"(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", date_str_cleaned)
                    if m_month_day_year:
                        month_name_str = m_month_day_year.group(1)
                        day_str = m_month_day_year.group(2)
                        year_str = m_month_day_year.group(3)
                        try:
                            day = int(day_str)
                            month = ENGLISH_MONTHS.get(month_name_str.lower())
                            year = int(year_str) if year_str else now_utc.year
                            if month and 1 <= day <= 31:
                                target_date = datetime.date(year, month, day)
                                # If no year was provided and the date is in the past, assume next year
                                if not year_str and target_date < now_utc.date():
                                    target_date = datetime.date(now_utc.year + 1, month, day)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not parse month/day/year from '{date_str_cleaned}': {e}")

    # 2. Parse Time String
    if time_str:
        time_str_cleaned = time_str.strip().lower()
        
        # Relative times like "in 30 minutes" - needs a base time
        m_relative_time = re.match(r"in\s+(half an hour|quarter hour|(\d+))\s+(hour|minute)s?", time_str_cleaned)
        if m_relative_time:
            value_str = m_relative_time.group(1) or m_relative_time.group(2)
            unit = m_relative_time.group(3)
            delta = timedelta()
            
            if value_str == "half an hour":
                value = 30
            elif value_str == "quarter hour":
                value = 15
            else:
                value = int(value_str)

            if unit == "hour":
                delta = timedelta(hours=value)
            elif unit == "minute":
                delta = timedelta(minutes=value)
            
            # Base time for relative calculation
            base_datetime_for_relative_time = datetime.combine(
                target_date if target_date else now_utc.date(), 
                time(0, 0)
            )
            if not target_date:  # if no date was given, relative time is from now
                base_datetime_for_relative_time = now_utc

            combined_dt = base_datetime_for_relative_time + delta
            target_date = combined_dt.date()
            target_time = combined_dt.time()
        
        if not target_time:  # If not parsed by relative logic above
            # Specific times like "9 am", "10:30 pm", "10 a.m.", "3:30 p.m."
            m_specific_time = re.match(r"^(\d{1,2})(?::(\d{1,2}))?\s*(a\.?m\.?|p\.?m\.?)?$", time_str_cleaned)
            if m_specific_time:
                hour_str = m_specific_time.group(1)
                minute_str = m_specific_time.group(2)
                period_str = m_specific_time.group(3)
                try:
                    hour = int(hour_str)
                    minute = int(minute_str) if minute_str else 0

                    if period_str:
                        # Normalize period string (remove dots and convert to lowercase)
                        period_normalized = period_str.lower().replace('.', '')
                        if period_normalized == "am" and hour == 12:
                            hour = 0  # 12 AM
                        elif period_normalized == "pm" and 1 <= hour < 12:
                            hour += 12
                    
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        target_time = time(hour, minute)
                    else:
                        logger.warning(f"Invalid hour/minute from parsed time: {time_str_cleaned}")

                except ValueError as e:
                    logger.warning(f"Invalid time components from regex: {time_str_cleaned} - {e}")
            else:
                # Time periods like "morning", "evening"
                for period, time_obj in ENGLISH_TIME_PERIODS.items():
                    if period in time_str_cleaned:
                        target_time = time_obj
                        break

    # 3. Combine date and time, convert to UTC
    # Important product rule: Do NOT auto-default when only date OR only time is provided.
    # - If only date is present (and no relative time resolved): ask user for time -> return None
    # - If only time is present (and no relative date resolved): ask user for date -> return None
    # - If both are present (or relative time produced both), return a concrete datetime.
    if target_date and target_time:
        # Combine date and time in user's timezone
        local_dt = datetime.combine(target_date, target_time)
        try:
            if user_timezone and user_timezone != 'UTC':
                tz_obj = pytz.timezone(user_timezone)
                local_dt_with_tz = tz_obj.localize(local_dt)
                utc_dt = local_dt_with_tz.astimezone(pytz.utc)
                logger.info(f"Converted {local_dt} from {user_timezone} to UTC: {utc_dt}")
            else:
                utc_dt = local_dt.replace(tzinfo=timezone.utc)
                logger.info(f"Treated {local_dt} as UTC: {utc_dt}")
        except Exception as e:
            logger.error(f"Error converting timezone from {user_timezone}: {e}")
            utc_dt = local_dt.replace(tzinfo=timezone.utc)
        return utc_dt
    elif target_date and not target_time:
        logger.info("parse_english_datetime_to_utc: Date provided without time -> returning None to trigger time clarification")
        return None
    elif target_time and not target_date:
        logger.info("parse_english_datetime_to_utc: Time provided without date -> returning None to trigger date clarification")
        return None
    else:
        # Neither date nor time specified
        return None
    
    # Unreachable, kept for clarity
    # return utc_dt

def resolve_english_date_phrase_to_range(phrase: Optional[str]) -> Optional[Tuple[datetime, datetime]]:
    """
    Resolves English date phrases to a date range.
    Example: "this week" -> (start_of_week, end_of_week)
    """
    if not phrase:
        return None
    
    phrase_lower = phrase.strip().lower()
    now_utc = get_current_utc_time()
    
    if phrase_lower == "today":
        start_date = now_utc.date()
        end_date = start_date
    elif phrase_lower == "tomorrow":
        start_date = (now_utc + timedelta(days=1)).date()
        end_date = start_date
    elif phrase_lower == "this week":
        # Start from Monday of current week
        days_since_monday = now_utc.weekday()
        start_date = (now_utc - timedelta(days=days_since_monday)).date()
        end_date = (start_date + timedelta(days=6))
    elif phrase_lower == "next week":
        # Start from Monday of next week
        days_since_monday = now_utc.weekday()
        start_date = (now_utc - timedelta(days=days_since_monday) + timedelta(days=7)).date()
        end_date = (start_date + timedelta(days=6))
    elif phrase_lower == "this month":
        start_date = now_utc.replace(day=1).date()
        # End of month (approximate)
        if now_utc.month == 12:
            end_date = now_utc.replace(year=now_utc.year + 1, month=1, day=1).date() - timedelta(days=1)
        else:
            end_date = now_utc.replace(month=now_utc.month + 1, day=1).date() - timedelta(days=1)
    else:
        return None
    
    start_dt = datetime.combine(start_date, datetime.time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.time.max).replace(tzinfo=timezone.utc)
    
    return (start_dt, end_dt)

def format_datetime_for_display(dt: Optional[datetime], user_timezone: str = 'UTC') -> str:
    """Format datetime for display in English, converting from UTC to user's timezone."""
    if dt is None:
        logger.warning("format_datetime_for_display called with None.")
        return "[Date/time unavailable]"
    try:
        # Convert UTC datetime to user's timezone for display
        if user_timezone and user_timezone != 'UTC':
            try:
                tz_obj = pytz.timezone(user_timezone)
                local_dt = dt.astimezone(tz_obj)
                logger.info(f"Converted {dt} UTC to {local_dt} {user_timezone} for display")
                return local_dt.strftime("%A, %B %d, %Y at %I:%M %p")
            except Exception as e:
                logger.error(f"Error converting timezone for display from {user_timezone}: {e}")
                # Fallback to UTC display
                return dt.strftime("%A, %B %d, %Y at %I:%M %p")
        else:
            # User timezone is UTC or not specified, display as UTC
            return dt.strftime("%A, %B %d, %Y at %I:%M %p")
    except Exception as e:
        logger.error(f"Error formatting datetime for display: {dt} ({type(dt)}): {e}", exc_info=True)
        return "[Invalid date/time]"

def format_date_for_display(dt: datetime) -> str:
    """Format date for display in English."""
    return dt.strftime("%A, %B %d, %Y")

def format_time_for_display(dt: datetime) -> str:
    """Format time for display in English."""
    return dt.strftime("%I:%M %p") 