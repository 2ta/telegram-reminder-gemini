import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict
import jdatetime
import pytz

logger = logging.getLogger(__name__)

TEHRAN_TZ = pytz.timezone('Asia/Tehran')

PERSIAN_TO_LATIN_NUMERALS: Dict[str, str] = {
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9' # Arabic numerals often used
}

JALALI_MONTHS: Dict[str, int] = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3,
    "تیر": 4, "مرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9,
    "دی": 10, "بهمن": 11, "اسفند": 12
}

PERSIAN_WEEKDAYS: Dict[str, int] = {
    "شنبه": 0,      # jdatetime.weekday() -> شنبه is 0
    "یکشنبه": 1,
    "دوشنبه": 2,
    "سه شنبه": 3,   # Note space for consistency with potential Gemini output
    "چهارشنبه": 4,
    "پنجشنبه": 5,
    "جمعه": 6
}

def _convert_persian_numerals_to_latin(text: str) -> str:
    if not text: return ""
    return "".join(PERSIAN_TO_LATIN_NUMERALS.get(char, char) for char in text)

# Approximate times for relative terms - these might need adjustment or context
# For now, let's assume Tehran timezone for local context before converting to UTC.
# Python's datetime objects are naive by default. jdatetime is also naive.
# We should aim to make them timezone-aware (e.g., Asia/Tehran) before converting to UTC.
# However, jdatetime itself doesn't directly support timezone objects in its constructors like datetime does.
# So, we'll handle jdatetime as naive local times, then localize to Asia/Tehran, then convert to UTC.

# It's better to get the current time within the function to ensure it's fresh.

# Helper to get current jdatetime and datetime localized to Tehran
def get_current_tehran_times() -> Tuple[jdatetime.datetime, datetime]:
    """Returns current Jalali datetime (naive) and current Gregorian datetime (aware, Tehran)."""
    now_jalali_naive = jdatetime.datetime.now() # This is naive, representing current local Jalali time
    now_gregorian_tehran_aware = datetime.now(TEHRAN_TZ)
    return now_jalali_naive, now_gregorian_tehran_aware


# Placeholder for time mapping
DEFAULT_TIMES = {
    "صبح": jdatetime.time(9, 0),    # 9:00 AM
    "ظهر": jdatetime.time(12, 30),  # 12:30 PM
    "بعد از ظهر": jdatetime.time(15, 0), # 3:00 PM
    "عصر": jdatetime.time(17, 0),    # 5:00 PM
    "غروب": jdatetime.time(18, 30),  # 6:30 PM (approx)
    "شب": jdatetime.time(21, 0),     # 9:00 PM
    "نصف شب": jdatetime.time(0, 0),   # Midnight
}

# This function will be the main parser.
# It will need to be significantly built out.
def parse_persian_datetime_to_utc(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    """
    Parses Persian date and time strings (extracted by Gemini) into a UTC datetime object.
    Example date_str: "فردا", "پس فردا", "سه شنبه", "۵ تیر", "1403/5/1"
    Example time_str: "ساعت ۱۰ صبح", "عصر", "نیم ساعت دیگه", "10:30"
    """
    now_jalali_local, _ = get_current_tehran_times()
    target_jalali_date: Optional[jdatetime.date] = None
    target_jalali_time: Optional[jdatetime.time] = None

    # Convert numerals in input strings first
    if date_str: date_str = _convert_persian_numerals_to_latin(date_str)
    if time_str: time_str = _convert_persian_numerals_to_latin(time_str)

    # 1. Parse Date String
    if date_str:
        date_str_cleaned = date_str.strip().lower() # Lowercase for easier matching
        if date_str_cleaned == "امروز":
            target_jalali_date = now_jalali_local.date()
        elif date_str_cleaned == "فردا":
            target_jalali_date = (now_jalali_local + timedelta(days=1)).date()
        elif date_str_cleaned == "پس فردا":
            target_jalali_date = (now_jalali_local + timedelta(days=2)).date()
        else:
            # Relative days/weeks/months: "X روز/هفته/ماه دیگه/بعد/آینده"
            m_relative = re.match(r"(\d+)\s+(روز|هفته|ماه)\s+(دیگه|بعد|آینده)", date_str_cleaned)
            if m_relative:
                value = int(m_relative.group(1))
                unit = m_relative.group(2)
                if unit == "روز":
                    target_jalali_date = (now_jalali_local + timedelta(days=value)).date()
                elif unit == "هفته":
                    target_jalali_date = (now_jalali_local + timedelta(weeks=value)).date()
                elif unit == "ماه": # Approximate, jdatetime doesn't have direct month adder
                    # This is a simplification; adding months correctly is complex.
                    # For now, assume 30 days per month for relative calc.
                    target_jalali_date = (now_jalali_local + timedelta(days=value * 30)).date()
            
            if not target_jalali_date:
                # Specific Jalali dates: YYYY/MM/DD or YYYY-MM-DD
                m_specific = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", date_str_cleaned)
                if m_specific:
                    try:
                        year, month, day = int(m_specific.group(1)), int(m_specific.group(2)), int(m_specific.group(3))
                        target_jalali_date = jdatetime.date(year, month, day)
                    except ValueError as e:
                        logger.warning(f"Invalid Jalali date components from regex: {date_str_cleaned} - {e}")
            
            if not target_jalali_date:
                # Weekdays: "شنبه", "شنبه آینده"
                # For "شنبه", it means next شنبه. If today is شنبه, it means next week's شنبه.
                for name, day_index in PERSIAN_WEEKDAYS.items():
                    if name in date_str_cleaned: # Use cleaned string
                        days_ahead = (day_index - now_jalali_local.weekday() + 7) % 7
                        if days_ahead == 0: # If it's today, make it next week unless specified "امروز"
                            if "امروز" not in date_str_cleaned:
                                days_ahead = 7 
                        target_jalali_date = (now_jalali_local + timedelta(days=days_ahead)).date()
                        break
            
            if not target_jalali_date:
                 # Dates like "۵ تیر" or "پنجم تیر ماه"
                m_month_day = re.match(r"(?:(\d{1,2})|(\S+))\s+(?:ماه\s+)?(\S+)", date_str_cleaned)
                if m_month_day:
                    day_str = m_month_day.group(1) or m_month_day.group(2) # group1 for digit, group2 for text day like پنجم
                    month_name_str = m_month_day.group(3)
                    try:
                        day = int(day_str) # Will need persian word to number for "پنجم"
                        month = JALALI_MONTHS.get(month_name_str.replace("ماه","").strip())
                        if month and 1 <= day <= 31:
                            target_jalali_date = jdatetime.date(now_jalali_local.year, month, day)
                            # If this date is in the past for the current year, assume next year
                            if target_jalali_date < now_jalali_local.date():
                                target_jalali_date = jdatetime.date(now_jalali_local.year + 1, month, day)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse day/month from '{date_str_cleaned}': {e}")

    # 2. Parse Time String
    if time_str:
        time_str_cleaned = time_str.strip().replace("ساعت", "").strip()
        # Relative times like "نیم ساعت دیگه" - needs a base time
        m_relative_time = re.match(r"(نیم|یه ربع|\d+)\s+(ساعت|دقیقه)\s+(دیگه|بعد|آینده)", time_str_cleaned)
        if m_relative_time:
            value_str = m_relative_time.group(1)
            unit = m_relative_time.group(2)
            delta = timedelta()
            if value_str == "نیم": value = 30
            elif value_str == "یه ربع": value = 15
            else: value = int(value_str)

            if unit == "ساعت": delta = timedelta(hours=value)
            elif unit == "دقیقه": delta = timedelta(minutes=value)
            
            # Base time for relative calculation: if a date was parsed, use start of that day, else use now.
            base_datetime_for_relative_time = jdatetime.datetime.combine(target_jalali_date if target_jalali_date else now_jalali_local.date(), jdatetime.time(0,0))
            if not target_jalali_date: # if no date was given, relative time is from now_jalali_local
                 base_datetime_for_relative_time = now_jalali_local

            combined_dt = base_datetime_for_relative_time + delta
            target_jalali_date = combined_dt.date()
            target_jalali_time = combined_dt.time()
        
        if not target_jalali_time: # If not parsed by relative logic above
            m_specific_time = re.match(r"^(\d{1,2})([:و](\d{1,2}))?(\s*(صبح|ظهر|بعد از ظهر|عصر|غروب|شب))?$", time_str_cleaned)
            if m_specific_time:
                hour_str = m_specific_time.group(1)
                minute_str = m_specific_time.group(3)
                period_str = m_specific_time.group(5)
                try:
                    hour = int(hour_str)
                    minute = int(minute_str) if minute_str else 0

                    if period_str:
                        period_str = period_str.strip()
                        if period_str == "صبح" and hour == 12: hour = 0 # 12 AM
                        elif period_str in ["بعد از ظهر", "عصر", "غروب", "شب"] and 1 <= hour < 12:
                            hour += 12
                    # Handle context-based time interpretation for evening terms like "امشب"
                    elif date_str and ("امشب" in date_str or "شب" in date_str) and 1 <= hour <= 11:
                        # If the date context is "tonight" and hour is 1-11 without AM/PM indicator, assume PM
                        hour += 12
                        logger.info(f"Date context '{date_str}' suggests evening - interpreting '{hour-12}' as {hour}:00 (PM)")
                    
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                         target_jalali_time = jdatetime.time(hour, minute)
                    else:
                        logger.warning(f"Invalid hour/minute from parsed time: {time_str_cleaned}")   

                except ValueError as e:
                    logger.warning(f"Invalid time components from regex: {time_str_cleaned} - {e}")
            else:
                # Check for keywords like "صبح", "عصر" if no numbers or more specific regex matched
                for name, time_val in DEFAULT_TIMES.items():
                    if name in time_str_cleaned:
                        target_jalali_time = time_val
                        break
    # 3. Combine Date and Time
    if not target_jalali_date and not target_jalali_time:
        logger.info(f"Could not parse a specific date or time from date_str='{date_str}', time_str='{time_str}'")
        return None

    if target_jalali_date and not target_jalali_time:
        target_jalali_time = DEFAULT_TIMES["صبح"]
        logger.debug(f"Only date was parsed ('{date_str}'), using default time: {target_jalali_time}")

    if not target_jalali_date and target_jalali_time:
        potential_datetime = jdatetime.datetime.combine(now_jalali_local.date(), target_jalali_time)
        if potential_datetime < now_jalali_local:
            target_jalali_date = (now_jalali_local + timedelta(days=1)).date()
            logger.debug(f"Only time ('{time_str}') was parsed, and it's in the past for today. Using tomorrow's date.")
        else:
            target_jalali_date = now_jalali_local.date()
            logger.debug(f"Only time ('{time_str}') was parsed. Using today's date.")

    if not target_jalali_date:
        logger.warning("Date part is still None after attempting to combine. This is unexpected.")
        return None 
        
    if not target_jalali_time:
         target_jalali_time = DEFAULT_TIMES["صبح"]

    final_jalali_datetime_naive = jdatetime.datetime.combine(target_jalali_date, target_jalali_time)

    gregorian_datetime_naive = final_jalali_datetime_naive.togregorian()

    # Manually define Tehran timezone offset (UTC+3:30). Not DST aware!
    # tehran_tzinfo = timezone(timedelta(hours=3, minutes=30), name="Asia/Tehran_Approx") # Old way
    
    # Localize the naive Gregorian datetime to Tehran using pytz
    try:
        # gregorian_datetime_tehran_aware = gregorian_datetime_naive.replace(tzinfo=tehran_tzinfo) # Old way
        gregorian_datetime_tehran_aware = TEHRAN_TZ.localize(gregorian_datetime_naive)
    except pytz.exceptions.AmbiguousTimeError as e:
        # This can happen during DST fall-back if 'is_dst=None' (default) is ambiguous
        # For reminders, we might prefer the earlier or later instance, or log and ask user.
        # For now, let's choose the first occurrence (is_dst=True often works, or handle specifically)
        logger.warning(f"Ambiguous time detected for {gregorian_datetime_naive} in Tehran: {e}. Attempting with is_dst=False.")
        try:
            gregorian_datetime_tehran_aware = TEHRAN_TZ.localize(gregorian_datetime_naive, is_dst=False)
        except Exception as e_dst_false:
            logger.error(f"Still ambiguous or error after trying is_dst=False for {gregorian_datetime_naive}: {e_dst_false}. Defaulting to UTC naive conversion.")
            # Fallback if localization is problematic, though this loses true local context for ambiguous times.
            # A better fallback might be to not set a reminder or ask for clarification.
            return gregorian_datetime_naive.replace(tzinfo=timezone.utc) # This is a last resort and not ideal.
    except pytz.exceptions.NonExistentTimeError as e:
        logger.error(f"Non-existent time detected for {gregorian_datetime_naive} in Tehran: {e}. This can happen during DST spring-forward.")
        # This datetime is invalid. We should not proceed with it.
        return None
    except Exception as e: # Catch other localization errors
        logger.error(f"Error localizing datetime {gregorian_datetime_naive} to Tehran: {e}")
        return None

    gregorian_datetime_utc = gregorian_datetime_tehran_aware.astimezone(timezone.utc)
    
    logger.info(f"Parsed date_str='{date_str}', time_str='{time_str}' into Jalali DT='{final_jalali_datetime_naive}', UTC DT='{gregorian_datetime_utc}'")
    return gregorian_datetime_utc

def resolve_persian_date_phrase_to_range(phrase: Optional[str]) -> Optional[Tuple[datetime, datetime]]:
    """
    Resolves a Persian date phrase like "امروز" (today) or "این هفته" (this week) 
    to a start and end datetime range in UTC.
    
    Args:
        phrase: A Persian date phrase to resolve
        
    Returns:
        A tuple of (start_datetime_utc, end_datetime_utc) if the phrase can be resolved,
        or None if the phrase cannot be resolved.
    """
    if not phrase:
        return None

    normalized_phrase = _convert_persian_numerals_to_latin(phrase.strip().lower())
    now_tehran = datetime.now(TEHRAN_TZ)
    today_tehran_start = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)

    start_dt_tehran: Optional[datetime] = None
    end_dt_tehran: Optional[datetime] = None

    if normalized_phrase == "امروز":
        start_dt_tehran = today_tehran_start
        end_dt_tehran = today_tehran_start + timedelta(days=1, microseconds=-1)
    elif normalized_phrase == "فردا":
        start_dt_tehran = today_tehran_start + timedelta(days=1)
        end_dt_tehran = start_dt_tehran + timedelta(days=1, microseconds=-1)
    elif normalized_phrase == "دیروز":
        start_dt_tehran = today_tehran_start - timedelta(days=1)
        end_dt_tehran = start_dt_tehran + timedelta(days=1, microseconds=-1)
    elif normalized_phrase == "این هفته":
        # jdatetime: Saturday is 0, Friday is 6
        # datetime: Monday is 0, Sunday is 6
        # We'll use jdatetime's convention for "week" (Sat-Fri)
        today_jalali = jdatetime.datetime.fromgregorian(datetime=now_tehran)
        days_from_saturday = today_jalali.weekday() # 0 for Sat, 1 for Sun, ...
        
        start_of_week_jalali = today_jalali - jdatetime.timedelta(days=days_from_saturday)
        start_dt_tehran_greg = start_of_week_jalali.togregorian()
        start_dt_tehran = TEHRAN_TZ.localize(
            datetime(start_dt_tehran_greg.year, start_dt_tehran_greg.month, start_dt_tehran_greg.day, 0, 0, 0)
        )
        end_dt_tehran = start_dt_tehran + timedelta(days=7, microseconds=-1)

    elif normalized_phrase == "هفته آینده" or normalized_phrase == "هفته بعد":
        today_jalali = jdatetime.datetime.fromgregorian(datetime=now_tehran)
        days_from_saturday = today_jalali.weekday()
        start_of_current_week_jalali = today_jalali - jdatetime.timedelta(days=days_from_saturday)
        start_of_next_week_jalali = start_of_current_week_jalali + jdatetime.timedelta(days=7)
        
        start_dt_tehran_greg = start_of_next_week_jalali.togregorian()
        start_dt_tehran = TEHRAN_TZ.localize(
            datetime(start_dt_tehran_greg.year, start_dt_tehran_greg.month, start_dt_tehran_greg.day, 0, 0, 0)
        )
        end_dt_tehran = start_dt_tehran + timedelta(days=7, microseconds=-1)

    elif normalized_phrase == "هفته گذشته" or normalized_phrase == "هفته قبل":
        today_jalali = jdatetime.datetime.fromgregorian(datetime=now_tehran)
        days_from_saturday = today_jalali.weekday()
        start_of_current_week_jalali = today_jalali - jdatetime.timedelta(days=days_from_saturday)
        start_of_last_week_jalali = start_of_current_week_jalali - jdatetime.timedelta(days=7)

        start_dt_tehran_greg = start_of_last_week_jalali.togregorian()
        start_dt_tehran = TEHRAN_TZ.localize(
            datetime(start_dt_tehran_greg.year, start_dt_tehran_greg.month, start_dt_tehran_greg.day, 0, 0, 0)
        )
        end_dt_tehran = start_dt_tehran + timedelta(days=7, microseconds=-1)
    
    # Add more cases: "ماه آینده", "ماه گذشته", "پس فردا", specific dates like "۵ آبان" etc.
    # For "۵ آبان", would need to assume current year or parse year.
    # For "صبح فردا", would need to adjust times.

    if start_dt_tehran and end_dt_tehran:
        start_utc = start_dt_tehran.astimezone(timezone.utc)
        end_utc = end_dt_tehran.astimezone(timezone.utc)
        logger.info(f"Resolved phrase \'{phrase}\' to UTC range: {start_utc} - {end_utc}")
        return start_utc, end_utc
    else:
        logger.warning(f"Could not resolve date phrase to a known range: \'{phrase}\'")
        return None

if __name__ == '__main__':
    # Basic tests (these should move to a proper test file)
    # For these tests to work well, we might need to mock get_current_tehran_times()
    # or pass a reference 'now' timestamp.

    logging.basicConfig(level=logging.DEBUG)

    # Assuming 'now' is 1403/04/20 10:00:00 for repeatable tests if we don't mock.
    # For actual testing, mocking 'now' is crucial.
    
    print(f"Test 'فردا', 'ساعت ۱۱ صبح': {parse_persian_datetime_to_utc('فردا', 'ساعت ۱۱ صبح')}")
    print(f"Test 'امروز', 'عصر': {parse_persian_datetime_to_utc('امروز', 'عصر')}")
    print(f"Test 'پس فردا', '۲ بعد از ظهر': {parse_persian_datetime_to_utc('پس فردا', '۲ بعد از ظهر')}")
    print(f"Test '1403/5/10', 'شب': {parse_persian_datetime_to_utc('1403/5/10', 'شب')}")
    print(f"Test None, 'ساعت ۱۵:۳۰': {parse_persian_datetime_to_utc(None, 'ساعت ۱۵:۳۰')}") # Should be today 15:30 or tomorrow if past
    print(f"Test 'فردا', None: {parse_persian_datetime_to_utc('فردا', None)}") # Should be tomorrow 9:00 AM
    print(f"Test None, None: {parse_persian_datetime_to_utc(None, None)}") # Should be None
    print(f"Test 'امروز', 'ساعت ۷ صبح': {parse_persian_datetime_to_utc('امروز', '۷ صبح')}")
    print(f"Test 'امروز', '7:00': {parse_persian_datetime_to_utc('امروز', '7:00')}") # Assumes latin digits for now
    print(f"Test '1403-06-01', '۱۸:۰۰': {parse_persian_datetime_to_utc('1403-06-01', '۱۸:۰۰')}")

    # Test case that would be in the past if "now" is 10 AM:
    # If now is 1403/04/20 10:00:00, then "امروز ساعت ۷ صبح" would result in 1403/04/20 07:00:00 UTC
    # (after Tehran offset and conversion), which is in the past relative to 10:00 Tehran time.
    # The current logic for "only time" handles if parsed time is past *for today*.
    # If a date and time are given that are in the past, it should return that past datetime.
    # The bot logic later can decide if a reminder for the past is valid. 