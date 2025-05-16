import jdatetime
import datetime
import pytz
import re
import logging
from typing import Union, Optional, Tuple

logger = logging.getLogger(__name__)

TEHRAN_TZ = pytz.timezone('Asia/Tehran')
UTC_TZ = pytz.utc

PERSIAN_MONTHS_TO_NUMBER = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3,
    "تیر": 4, "مرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9,
    "دی": 10, "بهمن": 11, "اسفند": 12
}

PERSIAN_WEEKDAYS_JALALI_OFFSET = {
    # jdatetime.weekday(): 0 for Saturday (شنبه), ..., 6 for Friday (جمعه)
    "شنبه": 0, "یک‌شنبه": 1, "یکشنبه": 1,
    "دوشنبه": 2, "سه‌شنبه": 3, "سه شنبه": 3, 
    "چهارشنبه": 4, "پنج‌شنبه": 5, "پنجشنبه": 5,
    "جمعه": 6,
}

def get_current_jalali_year() -> int:
    return jdatetime.datetime.now(TEHRAN_TZ).year

def normalize_persian_numerals(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    persian_to_english_numerals = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    # Also handle Arabic numerals if they appear
    arabic_to_english_numerals = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    text = text.translate(persian_to_english_numerals)
    text = text.translate(arabic_to_english_numerals)
    return text

def parse_persian_datetime_to_utc(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime.datetime]:
    if not date_str or not time_str:
        logger.warning(f"Date string or time string is missing for parsing. Date: '{date_str}', Time: '{time_str}'")
        return None

    original_date_str, original_time_str = date_str, time_str
    date_str = normalize_persian_numerals(date_str)
    time_str = normalize_persian_numerals(time_str) # Expects HH:MM
    logger.debug(f"Normalized inputs for parsing: date='{date_str}', time='{time_str}' (Originals: '{original_date_str}', '{original_time_str}')")

    now_jalali_tehran = jdatetime.datetime.now(TEHRAN_TZ)
    parsed_date_jalali_obj: Optional[jdatetime.date] = None

    try:
        # 1. Handle Persian relative dates
        if date_str == "امروز":
            parsed_date_jalali_obj = now_jalali_tehran.date()
        elif date_str == "فردا":
            parsed_date_jalali_obj = now_jalali_tehran.date() + jdatetime.timedelta(days=1)
        elif date_str == "پس فردا" or date_str == "پس‌فردا":
            parsed_date_jalali_obj = now_jalali_tehran.date() + jdatetime.timedelta(days=2)
        
        # 2. Handle "شنبه آینده" etc. (NLU might provide this from "next Saturday")
        elif parsed_date_jalali_obj is None and " آینده" in date_str:
            parts = date_str.split()
            if len(parts) == 2 and parts[1] == "آینده":
                target_weekday_name = parts[0]
                if target_weekday_name in PERSIAN_WEEKDAYS_JALALI_OFFSET:
                    target_jdatetime_weekday = PERSIAN_WEEKDAYS_JALALI_OFFSET[target_weekday_name]
                    current_jdatetime_weekday = now_jalali_tehran.weekday()
                    days_to_add = (target_jdatetime_weekday - current_jdatetime_weekday + 7) % 7
                    if days_to_add == 0: 
                        days_to_add = 7
                    parsed_date_jalali_obj = now_jalali_tehran.date() + jdatetime.timedelta(days=days_to_add)
                    logger.debug(f"Parsed '{original_date_str}' as next weekday: {parsed_date_jalali_obj}")

        # 3. Attempt to parse explicit Jalali date (e.g., "1403/02/20" or "1403-02-20")
        if parsed_date_jalali_obj is None:
            match_ymd_jalali = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", date_str)
            if match_ymd_jalali:
                try:
                    year, month, day = map(int, match_ymd_jalali.groups())
                    parsed_date_jalali_obj = jdatetime.date(year, month, day)
                    logger.debug(f"Parsed '{original_date_str}' as explicit Jalali YYYY/MM/DD: {parsed_date_jalali_obj}")
                except ValueError as e:
                    logger.warning(f"ValueError parsing explicit Jalali YYYY/MM/DD from '{date_str}': {e}")

        # 4. Attempt to parse textual Jalali date (e.g., "20 اردیبهشت 1403" or "۲۰ اردیبهشت")
        if parsed_date_jalali_obj is None:
            match_dmy_text = re.match(r"(\d{1,2})\s+([^\s\d]+)\s*(\d{4})?", date_str, re.UNICODE)
            if match_dmy_text:
                try:
                    day_str, month_name, year_str = match_dmy_text.groups()
                    day = int(day_str)
                    month = PERSIAN_MONTHS_TO_NUMBER.get(month_name)
                    if month:
                        year = int(year_str) if year_str else now_jalali_tehran.year
                        temp_jalali_date_for_check = jdatetime.date(year, month, day) # Check for validity
                        if not year_str and temp_jalali_date_for_check < now_jalali_tehran.date(): # if current year & past, assume next year
                            year += 1
                        parsed_date_jalali_obj = jdatetime.date(year, month, day)
                        logger.debug(f"Parsed '{original_date_str}' as textual Jalali: {parsed_date_jalali_obj}")
                    else:
                        logger.warning(f"Unknown Persian month name: '{month_name}' in '{original_date_str}'")
                except ValueError as e: # Catches errors from int() or jdatetime.date()
                    logger.warning(f"ValueError parsing textual Jalali from '{date_str}': {e}")
        
        # 5. Fallback: Attempt to parse as Gregorian YYYY-MM-DD
        if parsed_date_jalali_obj is None and '-' in date_str:
            match_ymd_gregorian = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str)
            if match_ymd_gregorian:
                try:
                    greg_year, greg_month, greg_day = map(int, match_ymd_gregorian.groups())
                    datetime.date(greg_year, greg_month, greg_day) # Validate components
                    greg_date_obj = datetime.date(greg_year, greg_month, greg_day)
                    parsed_date_jalali_obj = jdatetime.date.fromgregorian(date=greg_date_obj)
                    logger.info(f"Parsed '{original_date_str}' as Gregorian YYYY-MM-DD and converted to Jalali: {parsed_date_jalali_obj}")
                except ValueError:
                    logger.debug(f"Could not parse '{date_str}' as valid Gregorian YYYY-MM-DD.")

        if parsed_date_jalali_obj is None:
            logger.warning(f"Failed to parse date string: '{original_date_str}' (normalized: '{date_str}')")
            return None

        # Parse time "HH:MM"
        time_match = re.match(r"(\d{1,2}):(\d{1,2})", time_str)
        if not time_match:
            logger.warning(f"Could not parse time string: '{original_time_str}' (normalized: '{time_str}')")
            return None
        
        hour, minute = map(int, time_match.groups())
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            logger.warning(f"Invalid hour or minute in time: {hour}:{minute} from '{original_time_str}'")
            return None

        jalali_datetime_naive = jdatetime.datetime.combine(parsed_date_jalali_obj, jdatetime.time(hour, minute))
        gregorian_datetime_naive = jalali_datetime_naive.togregorian()
        dt_tehran_aware = TEHRAN_TZ.localize(gregorian_datetime_naive)
        dt_utc = dt_tehran_aware.astimezone(UTC_TZ)
        
        logger.info(f"Successfully parsed original date='{original_date_str}', time='{original_time_str}' to UTC: {dt_utc}")
        return dt_utc

    except Exception as e:
        logger.error(f"Unhandled exception in parse_persian_datetime_to_utc for date='{original_date_str if 'original_date_str' in locals() else date_str}', time='{original_time_str if 'original_time_str' in locals() else time_str}': {e}", exc_info=True)
        return None

def format_jalali_datetime_for_display(dt_utc: datetime.datetime) -> Tuple[str, str]:
    if not isinstance(dt_utc, datetime.datetime):
        logger.error(f"Invalid input for formatting: expected datetime, got {type(dt_utc)}")
        return "تاریخ نامعتبر", "زمان نامعتبر"
        
    if dt_utc.tzinfo is None or dt_utc.tzinfo.utcoffset(dt_utc) is None:
        logger.warning(f"format_jalali_datetime_for_display received naive datetime {dt_utc}, assuming UTC.")
        dt_utc = UTC_TZ.localize(dt_utc)

    dt_tehran = dt_utc.astimezone(TEHRAN_TZ)
    jalali_dt_from_gregorian = jdatetime.datetime.fromgregorian(datetime=dt_tehran)

    # Map English weekday names to Persian
    persian_weekdays = {
        0: "شنبه",       # Saturday
        1: "یکشنبه",     # Sunday
        2: "دوشنبه",     # Monday
        3: "سه‌شنبه",    # Tuesday
        4: "چهارشنبه",   # Wednesday
        5: "پنج‌شنبه",   # Thursday
        6: "جمعه"        # Friday
    }
    
    # Map English month names to Persian
    persian_months = {
        1: "فروردین",
        2: "اردیبهشت",
        3: "خرداد",
        4: "تیر",
        5: "مرداد",
        6: "شهریور",
        7: "مهر",
        8: "آبان",
        9: "آذر",
        10: "دی",
        11: "بهمن",
        12: "اسفند"
    }
    
    # Get the Persian weekday, day, month, and year
    weekday = persian_weekdays[jalali_dt_from_gregorian.weekday()]
    day = jalali_dt_from_gregorian.day
    month = persian_months[jalali_dt_from_gregorian.month]
    year = jalali_dt_from_gregorian.year
    
    # Format the date in Persian
    date_display = f"{weekday}، {day} {month} {year}"
    time_display = jalali_dt_from_gregorian.strftime("%H:%M")
    
    return date_display, time_display

def calculate_relative_reminder_time(primary_event_time_utc: datetime.datetime, relative_offset_description: str) -> Optional[datetime.datetime]:
    """Calculates the actual reminder datetime based on a primary event time and a relative offset string."""
    if not primary_event_time_utc or not relative_offset_description:
        return None

    normalized_offset = normalize_persian_numerals(relative_offset_description.lower())
    delta = None

    # Simple parsing for now, can be expanded with more regex or a dedicated library
    # Example: "نیم ساعت قبل", "30 دقیقه بعد", "1 ساعت قبل"
    
    match_minutes = re.search(r'(\d+|یک|دو|نیم) +دقیقه', normalized_offset)
    match_hours = re.search(r'(\d+|یک|دو|نیم) +ساعت', normalized_offset)

    value = 0
    unit = None

    if match_minutes:
        value_str = match_minutes.group(1)
        unit = "minutes"
    elif match_hours:
        value_str = match_hours.group(1)
        unit = "hours"
    else:
        logger.warning(f"Could not parse time unit from relative offset: {relative_offset_description}")
        return None

    if value_str == "نیم":
        value = 30 if unit == "minutes" else 0.5 # 0.5 hours
    elif value_str == "یک":
        value = 1
    elif value_str == "دو":
        value = 2
    else:
        try:
            value = int(value_str)
        except ValueError:
            logger.error(f"Could not parse numeric value from relative offset: {value_str} in {relative_offset_description}")
            return None
    
    if unit == "minutes":
        delta = datetime.timedelta(minutes=value)
    elif unit == "hours":
        delta = datetime.timedelta(hours=value)
    
    if delta is None:
        return None

    if "قبل" in normalized_offset:
        return primary_event_time_utc - delta
    elif "بعد" in normalized_offset:
        return primary_event_time_utc + delta
    else: # Default to 'بعد' if neither is specified, or handle as error
        logger.warning(f"Direction (قبل/بعد) not specified or recognized in: {relative_offset_description}. Assuming 'بعد'.")
        return primary_event_time_utc + delta
    # Fallback if no clear direction
    # logger.warning(f"Could not determine 'before' or 'after' from offset: {relative_offset_description}")
    # return None

def resolve_persian_date_phrase_to_range(phrase: Optional[str]) -> Optional[Tuple[datetime.datetime, datetime.datetime]]:
    if not phrase:
        return None

    normalized_phrase = normalize_persian_numerals(phrase.strip().lower())
    now_tehran = datetime.datetime.now(TEHRAN_TZ)
    today_tehran_start = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)

    start_dt_tehran: Optional[datetime.datetime] = None
    end_dt_tehran: Optional[datetime.datetime] = None

    if normalized_phrase == "امروز":
        start_dt_tehran = today_tehran_start
        end_dt_tehran = today_tehran_start + datetime.timedelta(days=1, microseconds=-1)
    elif normalized_phrase == "فردا":
        start_dt_tehran = today_tehran_start + datetime.timedelta(days=1)
        end_dt_tehran = start_dt_tehran + datetime.timedelta(days=1, microseconds=-1)
    elif normalized_phrase == "دیروز":
        start_dt_tehran = today_tehran_start - datetime.timedelta(days=1)
        end_dt_tehran = start_dt_tehran + datetime.timedelta(days=1, microseconds=-1)
    elif normalized_phrase == "این هفته":
        # jdatetime: Saturday is 0, Friday is 6
        # datetime: Monday is 0, Sunday is 6
        # We'll use jdatetime's convention for "week" (Sat-Fri)
        today_jalali = jdatetime.datetime.fromgregorian(datetime=now_tehran)
        days_from_saturday = today_jalali.weekday() # 0 for Sat, 1 for Sun, ...
        
        start_of_week_jalali = today_jalali - jdatetime.timedelta(days=days_from_saturday)
        start_dt_tehran_greg = start_of_week_jalali.togregorian()
        start_dt_tehran = TEHRAN_TZ.localize(
            datetime.datetime(start_dt_tehran_greg.year, start_dt_tehran_greg.month, start_dt_tehran_greg.day, 0, 0, 0)
        )
        end_dt_tehran = start_dt_tehran + datetime.timedelta(days=7, microseconds=-1)

    elif normalized_phrase == "هفته آینده" or normalized_phrase == "هفته بعد":
        today_jalali = jdatetime.datetime.fromgregorian(datetime=now_tehran)
        days_from_saturday = today_jalali.weekday()
        start_of_current_week_jalali = today_jalali - jdatetime.timedelta(days=days_from_saturday)
        start_of_next_week_jalali = start_of_current_week_jalali + jdatetime.timedelta(days=7)
        
        start_dt_tehran_greg = start_of_next_week_jalali.togregorian()
        start_dt_tehran = TEHRAN_TZ.localize(
             datetime.datetime(start_dt_tehran_greg.year, start_dt_tehran_greg.month, start_dt_tehran_greg.day, 0, 0, 0)
        )
        end_dt_tehran = start_dt_tehran + datetime.timedelta(days=7, microseconds=-1)

    elif normalized_phrase == "هفته گذشته" or normalized_phrase == "هفته قبل":
        today_jalali = jdatetime.datetime.fromgregorian(datetime=now_tehran)
        days_from_saturday = today_jalali.weekday()
        start_of_current_week_jalali = today_jalali - jdatetime.timedelta(days=days_from_saturday)
        start_of_last_week_jalali = start_of_current_week_jalali - jdatetime.timedelta(days=7)

        start_dt_tehran_greg = start_of_last_week_jalali.togregorian()
        start_dt_tehran = TEHRAN_TZ.localize(
            datetime.datetime(start_dt_tehran_greg.year, start_dt_tehran_greg.month, start_dt_tehran_greg.day, 0, 0, 0)
        )
        end_dt_tehran = start_dt_tehran + datetime.timedelta(days=7, microseconds=-1)
    
    # Add more cases: "ماه آینده", "ماه گذشته", "پس فردا", specific dates like "۵ آبان" etc.
    # For "۵ آبان", would need to assume current year or parse year.
    # For "صبح فردا", would need to adjust times.
    # parsed_specific_date = parse_persian_datetime_to_utc(normalized_phrase, "00:00") # Check if it's a specific date like "۵ آبان"
    # if parsed_specific_date and not (start_dt_tehran and end_dt_tehran): # if not already handled by relative
    #     # This gives a single point in time. We need to make it a full day range in Tehran time.
    #     # Convert the UTC point back to Tehran time to get the day's boundaries in Tehran.
    #     dt_tehran_specific_day_start = parsed_specific_date.astimezone(TEHRAN_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    #     start_dt_tehran = dt_tehran_specific_day_start
    #     end_dt_tehran = start_dt_tehran + datetime.timedelta(days=1, microseconds=-1)


    if start_dt_tehran and end_dt_tehran:
        start_utc = start_dt_tehran.astimezone(UTC_TZ)
        end_utc = end_dt_tehran.astimezone(UTC_TZ)
        logger.info(f"Resolved phrase \'{phrase}\' to UTC range: {start_utc} - {end_utc}")
        return start_utc, end_utc
    else:
        logger.warning(f"Could not resolve date phrase to a known range: \'{phrase}\'")
        return None

# ... (keep the if __name__ == '__main__': test block from the previous utils.py version for your own testing) ...
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(message)s")
    logger.info("Testing date/time utilities...")
    # (Add the comprehensive test cases from the previous utils.py version here)