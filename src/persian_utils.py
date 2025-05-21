"""
Persian formatting utilities for the Telegram Reminder Bot
"""
import jdatetime

def to_persian_numerals(text: str) -> str:
    """Convert English/Arabic numerals to Persian numerals"""
    persian_numerals_map = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return str(text).translate(persian_numerals_map)  # Ensure input is string

def get_persian_day_name(jalali_date):
    """Get the Persian day name from a Jalali date object"""
    # Define the Persian day names directly to avoid potential attribute errors
    persian_days = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
    english_days = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    try:
        # First try to get the day index numerically
        day_index = jalali_date.weekday()
        # Map 0=Saturday, 1=Sunday, ... 6=Friday
        return persian_days[day_index]
    except (AttributeError, TypeError):
        try:
            # Try jweekday() if regular weekday() doesn't exist
            day_value = jalali_date.jweekday()
            
            if isinstance(day_value, int):
                # If it's already an index, use it directly
                return persian_days[day_value]
            elif isinstance(day_value, str):
                # If it's a string like "Thursday", find its index in English names
                try:
                    day_index = english_days.index(day_value)
                    return persian_days[day_index]
                except ValueError:
                    # If it's not in our English list, try a case-insensitive comparison
                    day_value_lower = day_value.lower()
                    for i, day in enumerate(english_days):
                        if day.lower() == day_value_lower:
                            return persian_days[i]
                    # If still not found, try to see if it's a direct Persian day name
                    if day_value in persian_days:
                        return day_value
                    # Last resort - return a generic day placeholder
                    return "روز"
            else:
                # Unexpected type, return generic day
                return "روز"
        except (AttributeError, TypeError):
            # If all else fails, return a generic day placeholder
            return "روز"

def get_persian_month_name(jalali_date):
    """Get the Persian month name from a Jalali date object"""
    # Define Persian month names directly to be safe
    persian_months = [
        'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
        'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
    ]
    
    try:
        # Try to get month as an integer (1-12)
        month_num = jalali_date.month
        # Adjust to 0-index for our array
        return persian_months[month_num - 1]
    except (AttributeError, TypeError, IndexError):
        # If there's any problem, return a generic month placeholder
        return "ماه"

def format_jalali_date(jalali_date):
    """Format a Jalali date with day name, day, month, year in Persian format"""
    persian_day_name = get_persian_day_name(jalali_date)
    persian_day_num = to_persian_numerals(str(jalali_date.day))
    persian_month_name = get_persian_month_name(jalali_date)
    persian_year_num = to_persian_numerals(str(jalali_date.year))
    
    return f"{persian_day_name} {persian_day_num} {persian_month_name} {persian_year_num}" 