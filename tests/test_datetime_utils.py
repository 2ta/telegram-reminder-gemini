import pytest
from datetime import datetime, timedelta, timezone
import jdatetime
import pytz # Added for TEHRAN_TZ
from unittest.mock import patch, MagicMock

from src.datetime_utils import parse_persian_datetime_to_utc, get_current_tehran_times, DEFAULT_TIMES

# Define a fixed "now" for testing. This Jalali datetime corresponds to:
# Gregorian: 2024-07-20 10:00:00 (assuming this is Tehran time for jdatetime.now() mock)
MOCK_NOW_JALALI = jdatetime.datetime(1403, 4, 30, 10, 0, 0) # 30 Tir 1403, 10:00 AM, which is a Saturday

# Corresponding Gregorian time in Tehran for MOCK_NOW_JALALI
TEHRAN_TZ = pytz.timezone('Asia/Tehran')
MOCK_NOW_GREGORIAN_TEHRAN_AWARE = TEHRAN_TZ.localize(MOCK_NOW_JALALI.togregorian()) # 2024-07-20 10:00:00+03:30

# Corresponding UTC time
MOCK_NOW_UTC = MOCK_NOW_GREGORIAN_TEHRAN_AWARE.astimezone(pytz.utc) # 2024-07-20 06:30:00+00:00

@pytest.fixture
def mock_get_current_tehran_times_fixture(): # Renamed to avoid conflict if we import the real one
    # The function now returns a tuple: (naive_jalali_now, aware_gregorian_tehran_now)
    with patch('src.datetime_utils.get_current_tehran_times', return_value=(MOCK_NOW_JALALI, MOCK_NOW_GREGORIAN_TEHRAN_AWARE)) as mock:
        yield mock

# Expected Tehran timezone (approximate, as used in the utility)
TEHRAN_APPROX_TZ = timezone(timedelta(hours=3, minutes=30))

# Test cases
# Format: (test_id, date_str, time_str, expected_utc_datetime_or_none)
# To calculate expected_utc_datetime:
# 1. Determine target Jalali datetime (naive)
# 2. Convert to Gregorian datetime (naive)
# 3. Localize to Tehran (e.g., using pytz 'Asia/Tehran')
# 4. Convert to UTC (using pytz.utc)

# Mock now: 1403/4/30 10:00:00 (Saturday, 2024-07-20 10:00:00 Tehran time / 06:30:00 UTC)

TEST_CASES = [
    # Existing cases (re-verified, some might need slight adjustment if default assumptions changed)
    ("tomorrow_11am", "فردا", "ساعت ۱۱ صبح", datetime(2024, 7, 22, 7, 30, 0, tzinfo=pytz.utc)), # 1403/5/1 11:00 Teh -> 2024-07-22 11:00 Teh -> 07:30 UTC
    ("today_afternoon", "امروز", "عصر", datetime(2024, 7, 20, 13, 30, 0, tzinfo=pytz.utc)),         # 1403/4/30 17:00 Teh -> 13:30 UTC
    ("day_after_tomorrow_2pm", "پس فردا", "۲ بعد از ظهر", datetime(2024, 7, 23, 10, 30, 0, tzinfo=pytz.utc)), # 1403/5/2 14:00 Teh -> 10:30 UTC
    ("specific_jalali_date_night", "1403/5/10", "شب", datetime(2024, 7, 31, 17, 30, 0, tzinfo=pytz.utc)),    # 1403/5/10 21:00 Teh -> 17:30 UTC
    ("time_only_future_today", None, "ساعت ۱۵:۳۰", datetime(2024, 7, 20, 12, 0, 0, tzinfo=pytz.utc)),     # 1403/4/30 15:30 Teh -> 12:00 UTC
    ("time_only_past_today_so_tomorrow", None, "ساعت ۷ صبح", datetime(2024, 7, 21, 3, 30, 0, tzinfo=pytz.utc)), # 1403/4/31 07:00 Teh -> 03:30 UTC
    ("date_only_default_time", "فردا", None, datetime(2024, 7, 22, 5, 30, 0, tzinfo=pytz.utc)), # Default time 9:00 AM Teh (DEFAULT_TIMES["پیش فرض"]) -> 05:30 UTC
    ("no_date_no_time", None, None, None),
    ("specific_jalali_hyphen", "1403-06-01", "۱۸:۰۰", datetime(2024, 8, 22, 14, 30, 0, tzinfo=pytz.utc)), # 1403/6/1 18:00 Teh -> 14:30 UTC
    ("today_7am_explicit_latin_digits", "امروز", "7:00", datetime(2024, 7, 20, 3, 30, 0, tzinfo=pytz.utc)), # 1403/4/30 07:00 Teh -> 03:30 UTC (Was this right? 7:00 is before 10:00)
                                                                                                           # Yes, because "امروز" pins the date. Time can be past or future on that day.

    # Test specific cleaning and regex for time (these should be using Persian numerals now too if applicable)
    ("time_keyword_with_persian_number_morning", "امروز", "ساعت ۱۰ صبح", datetime(2024, 7, 20, 6, 30, 0, tzinfo=pytz.utc)), # 10:00 Teh -> 06:30 UTC
    ("time_keyword_with_persian_number_afternoon", "امروز", "ساعت ۲ بعد از ظهر", datetime(2024, 7, 20, 10, 30, 0, tzinfo=pytz.utc)), # 14:00 Teh -> 10:30 UTC
    ("time_keyword_persian_night_number", "امروز", "۹ شب", datetime(2024, 7, 20, 17, 30, 0, tzinfo=pytz.utc)),       # 21:00 Teh -> 17:30 UTC

    # New Test Cases for Enhanced Features
    # 1. Persian Numerals
    ("persian_num_date_time", "۱۴۰۳/۰۵/۰۱", "ساعت ۱۱ و ۳۰ دقیقه", datetime(2024, 7, 22, 8, 0, 0, tzinfo=pytz.utc)), # 1403/5/1 11:30 Teh -> 08:00 UTC
    ("persian_num_time_only_pm", "امروز", "ساعت ۷ و ۲۰ دقیقه عصر", datetime(2024, 7, 20, 15, 50, 0, tzinfo=pytz.utc)), # 19:20 Teh -> 15:50 UTC

    # 2. Relative Dates ("X روز/هفته/ماه دیگه")
    ("3_days_later_time_keyword", "۳ روز دیگه", "عصر", datetime(2024, 7, 23, 13, 30, 0, tzinfo=pytz.utc)), # 1403/4/30 + 3d = 1403/5/2 (2024-07-23) 17:00 Teh -> 13:30 UTC
    ("2_weeks_later_specific_time", "دو هفته آینده", "۱۰:۳۰", datetime(2024, 8, 3, 7, 0, 0, tzinfo=pytz.utc)), # 1403/4/30 + 14d = 1403/5/13 (2024-08-03) 10:30 Teh -> 07:00 UTC
    ("1_month_later_time_keyword", "یک ماه بعد", "ظهر", datetime(2024, 8, 19, 9, 0, 0, tzinfo=pytz.utc)), # 1403/4/30 + 30d = 1403/5/29 (2024-08-19) 12:30 Teh -> 09:00 UTC (using Jalali month logic it would be 1403/5/30)
                                                                                                    # The code uses timedelta(days=num_months * 30) so 1403/5/29 is correct for "1 month".
                                                                                                    # jdatetime(1403,4,30) + timedelta(days=30) = jdatetime(1403,5,29)

    # 3. Weekday Parsing (MOCK_NOW_JALALI is 1403/4/30 - Saturday)
    ("next_monday_10am", "دوشنبه", "۱۰ صبح", datetime(2024, 7, 22, 6, 30, 0, tzinfo=pytz.utc)), # Next Mon from Sat 1403/4/30 is 1403/5/1 (2024-07-22) 10:00 Teh -> 06:30 UTC
    ("next_saturday_3pm", "شنبه آینده", "۱۵:۰۰", datetime(2024, 7, 27, 11, 30, 0, tzinfo=pytz.utc)), # Next Sat from Sat 1403/4/30 is 1403/5/6 (2024-07-27) 15:00 Teh -> 11:30 UTC
    ("keyword_shanbeh_today_is_shanbeh_means_next", "شنبه", "۱۱ صبح", datetime(2024, 7, 27, 7, 30, 0, tzinfo=pytz.utc)), # "شنبه" when today is Sat -> next Sat, 1403/5/6 11:00 Teh -> 07:30 UTC
    ("explicit_today_saturday_3pm", "شنبه امروز", "۳ بعد از ظهر", datetime(2024, 7, 20, 11, 30, 0, tzinfo=pytz.utc)), # Sat 1403/4/30 15:00 Teh -> 11:30 UTC
    ("next_friday_no_time", "جمعه آینده", None, datetime(2024, 7, 26, 5, 30, 0, tzinfo=pytz.utc)), # Next Fri 1403/5/4, default time 9:00 Teh -> 05:30 UTC

    # 4. Day-Month Name Parsing (MOCK_NOW_JALALI is 1403/4/30)
    # "۵ تیر" means 5 Tir. Current 30 Tir. So 5 Tir of current year (1403/4/5) is past. -> 1404/4/5
    ("5_tir_next_year_2pm", "۵ تیر", "۲ بعد از ظهر", datetime(2025, 6, 26, 10, 30, 0, tzinfo=pytz.utc)), # 1404/4/5 14:00 Teh -> 2025-06-26 14:00 Teh -> 10:30 UTC
    ("10_mordad_this_year_9am", "۱۰ مرداد", "۹ صبح", datetime(2024, 7, 31, 5, 30, 0, tzinfo=pytz.utc)), # 1403/5/10 09:00 Teh -> 05:30 UTC
    ("2_esfand_this_year_no_time", "۲ اسفند", None, datetime(2025, 2, 20, 5, 30, 0, tzinfo=pytz.utc)), # 1403/12/2 09:00 Teh (default time) -> 2025-02-20 09:00 Teh -> 05:30 UTC

    # 5. Relative Time Phrases
    ("half_hour_later_from_now_no_date", None, "نیم ساعت دیگه", datetime(2024, 7, 20, 7, 0, 0, tzinfo=pytz.utc)), # 10:00 (now) + 30m = 10:30 Teh -> 07:00 UTC
    ("one_hour_later_tomorrow_date", "فردا", "یه ساعت دیگه", datetime(2024, 7, 21, 21, 30, 0, tzinfo=pytz.utc)), # فردا (1403/5/1), time "یه ساعت دیگه" is 01:00 on 1403/5/1. 2024-07-22 01:00 Teh -> 2024-07-21 21:30 UTC
    ("quarter_to_8_no_date_future", None, "یه ربع به ۸", datetime(2024, 7, 21, 4, 15, 0, tzinfo=pytz.utc)), # 07:45 next day (1403/4/31) as 07:45 today is past. -> 04:15 UTC
    ("quarter_to_8_no_date_today_future_variant", None, "ساعت یه ربع به ۸", datetime(2024, 7, 21, 4, 15, 0, tzinfo=pytz.utc)), # Same as above
    ("20_mins_past_10_evening_specified_date", "پس فردا", "۱۰ و ۲۰ دقیقه شب", datetime(2024, 7, 23, 18, 50, 0, tzinfo=pytz.utc)), # پس فردا (1403/5/2) 22:20 Teh -> 18:50 UTC

    # More time parsing variations
    ("time_8_pm_variant_persian_num", "امروز", "ساعت ۸ شب", datetime(2024, 7, 20, 16, 30, 0, tzinfo=pytz.utc)),   # 20:00 Teh -> 16:30 UTC
    ("time_12_30_pm_explicit_persian_num", "امروز", "۱۲ و ۳۰ دقیقه ظهر", datetime(2024, 7, 20, 9, 0, 0, tzinfo=pytz.utc)),# 12:30 Teh -> 09:00 UTC

    # Invalid/Edge cases
    ("invalid_date_string", "فردا پسین روز", "۱۲ ظهر", None), # Gibberish date
    ("invalid_time_string", "فردا", "ظهر و نیم", None), # Gibberish time
    ("time_only_default_to_today_if_not_passed_already", None, "ساعت ۱۱", datetime(2024, 7, 20, 7, 30, 0, tzinfo=pytz.utc)), # 11:00 today, since 10:00 is now. 11:00 Teh -> 07:30 UTC
]

@pytest.mark.parametrize("test_id, date_str, time_str, expected_utc", TEST_CASES)
def test_parse_persian_datetime(test_id, date_str, time_str, expected_utc, mock_get_current_tehran_times_fixture): # Use the renamed fixture
    result_utc = parse_persian_datetime_to_utc(date_str, time_str)
    if expected_utc is None:
        assert result_utc is None, f"Test ID '{test_id}' failed. Expected None, got {result_utc}"
    else:
        assert result_utc is not None, f"Test ID '{test_id}' failed: result is None, expected {expected_utc}"
        # Ensure tzinfo is pytz.utc for proper comparison
        expected_utc_aware = expected_utc.astimezone(pytz.utc) if expected_utc.tzinfo is None else expected_utc
        
        assert result_utc.year == expected_utc_aware.year, f"Test ID '{test_id}' failed (year). Got {result_utc.year}, expected {expected_utc_aware.year}"
        assert result_utc.month == expected_utc_aware.month, f"Test ID '{test_id}' failed (month). Got {result_utc.month}, expected {expected_utc_aware.month}"
        assert result_utc.day == expected_utc_aware.day, f"Test ID '{test_id}' failed (day). Got {result_utc.day}, expected {expected_utc_aware.day}"
        assert result_utc.hour == expected_utc_aware.hour, f"Test ID '{test_id}' failed (hour). Got {result_utc.hour}, expected {expected_utc_aware.hour}"
        assert result_utc.minute == expected_utc_aware.minute, f"Test ID '{test_id}' failed (minute). Got {result_utc.minute}, expected {expected_utc_aware.minute}"
        # Seconds might not always be zero if not specified, default to 0 for comparison if expected has 0
        assert result_utc.second == expected_utc_aware.second or expected_utc_aware.second == 0, f"Test ID '{test_id}' failed (second). Got {result_utc.second}, expected {expected_utc_aware.second}"
        assert result_utc.tzinfo == pytz.utc, f"Test ID '{test_id}' failed (tzinfo). Got {result_utc.tzinfo}, expected {pytz.utc}"
        # For more robust comparison:
        assert result_utc == expected_utc_aware, f"Test ID '{test_id}' failed. Got {result_utc}, expected {expected_utc_aware}"

def test_get_current_tehran_times_returns_correct_types():
    # Test the actual get_current_tehran_times without mock to ensure it runs and returns correct types
    jalali_now, gregorian_tehran_aware_now = get_current_tehran_times()
    
    assert isinstance(jalali_now, jdatetime.datetime)
    assert jalali_now.tzinfo is None, "Jalali datetime should be naive"
    
    assert isinstance(gregorian_tehran_aware_now, datetime)
    assert gregorian_tehran_aware_now.tzinfo is not None, "Gregorian datetime should be timezone-aware"
    assert gregorian_tehran_aware_now.tzinfo.zone == 'Asia/Tehran', "Gregorian datetime should be in Asia/Tehran timezone"

# Updated TODOs:
# - Consider testing for AmbiguousTimeError / NonExistentTimeError if specific dates known to cause them are used.
#   (Requires careful selection of dates/times around DST changes for Tehran, if applicable and handled by pytz)
# - Test that _convert_persian_numerals_to_latin handles mixed strings correctly.
# - Test more variations of "شنبه" vs "شنبه آینده" vs "شنبه امروز" to ensure robustness.
# - Test specific regex captures within _parse_time_string if it becomes more complex.
# - Add tests for Jalali month number parsing ("ماه ۵", "برج ۳") if supported in future.
# - Test parsing "آخر هفته", "وسط هفته" if implemented. 