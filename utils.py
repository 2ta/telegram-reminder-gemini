import jdatetime
import datetime
import pytz
import re
import logging

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

def normalize_persian_numerals(text: str | None) -> str | None:
    if text is None:
        return None
    persian_to_english_numerals = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    # Also handle Arabic numerals if they appear
    arabic_to_english_numerals = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    text = text.translate(persian_to_english_numerals)
    text = text.translate(arabic_to_english_numerals)
    return text

def parse_persian_datetime_to_utc(date_str: str | None, time_str: str | None) -> datetime.datetime | None:
    if not date_str or not time_str:
        logger.warning(f"Date string or time string is missing for parsing. Date: '{date_str}', Time: '{time_str}'")
        return None

    original_date_str, original_time_str = date_str, time_str
    date_str = normalize_persian_numerals(date_str)
    time_str = normalize_persian_numerals(time_str) # Expects HH:MM
    logger.debug(f"Normalized inputs for parsing: date='{date_str}', time='{time_str}' (Originals: '{original_date_str}', '{original_time_str}')")

    now_jalali_tehran = jdatetime.datetime.now(TEHRAN_TZ)
    parsed_date_jalali_obj: jdatetime.date | None = None

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

def format_jalali_datetime_for_display(dt_utc: datetime.datetime) -> tuple[str, str]:
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

# ... (keep the if __name__ == '__main__': test block from the previous utils.py version for your own testing) ...
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(message)s")
    logger.info("Testing date/time utilities...")
    # (Add the comprehensive test cases from the previous utils.py version here)