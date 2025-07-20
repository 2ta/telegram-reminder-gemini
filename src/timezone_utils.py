import requests
import google.generativeai as genai
from typing import Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Configure Gemini
try:
    from config.config import settings
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
except ImportError:
    logger.warning("Gemini API key not configured. City name timezone detection will not work.")
    model = None

def get_timezone_from_city_gemini(city_name: str) -> Optional[str]:
    """Use Gemini LLM to infer timezone from city name."""
    if not model:
        return None
    
    try:
        prompt = f"""
        Given the city name "{city_name}", return only the IANA timezone identifier (e.g., "America/New_York", "Europe/London", "Asia/Tehran").
        
        Rules:
        1. Return only the timezone identifier, nothing else
        2. Use standard IANA timezone names
        3. If the city name is ambiguous, choose the most common/popular city
        4. If you can't determine the timezone or the city name is invalid/gibberish, return "INVALID"
        
        Examples:
        - "New York" → "America/New_York"
        - "London" → "Europe/London"
        - "Tehran" → "Asia/Tehran"
        - "Tokyo" → "Asia/Tokyo"
        - "Sydney" → "Australia/Sydney"
        - "lksakd" → "INVALID"
        - "xyz123" → "INVALID"
        
        City: {city_name}
        Timezone:"""
        
        response = model.generate_content(prompt)
        timezone = response.text.strip()
        
        # Check if Gemini returned INVALID
        if timezone == "INVALID" or timezone == "":
            logger.info(f"Gemini could not determine timezone for invalid city '{city_name}'")
            return None
        
        # Validate the timezone
        if is_valid_timezone(timezone):
            logger.info(f"Gemini detected timezone '{timezone}' for city '{city_name}'")
            return timezone
        else:
            logger.warning(f"Gemini returned invalid timezone '{timezone}' for city '{city_name}'")
            return None
            
    except Exception as e:
        logger.error(f"Error getting timezone from Gemini for city '{city_name}': {e}")
        return None

def get_timezone_from_location(lat: float, lon: float) -> Optional[str]:
    """Get timezone from lat/lon using timezonefinder or fallback to manual mapping."""
    try:
        # Try to use timezonefinder library first
        try:
            from timezonefinder import TimezoneFinder
            tf = TimezoneFinder()
            timezone = tf.timezone_at(lat=lat, lng=lon)
            if timezone and is_valid_timezone(timezone):
                logger.info(f"TimezoneFinder detected timezone '{timezone}' for coordinates ({lat}, {lon})")
                return timezone
        except ImportError:
            logger.warning("TimezoneFinder not available, using manual mapping")
        
        # Fallback: Manual mapping for common regions
        # Tehran, Iran coordinates: ~35.6892, 51.3890
        if 35.0 <= lat <= 36.0 and 51.0 <= lon <= 52.0:
            timezone = "Asia/Tehran"
            logger.info(f"Manual mapping detected Tehran timezone for coordinates ({lat}, {lon})")
            return timezone
        
        # New York coordinates: ~40.7128, -74.0060
        if 40.0 <= lat <= 41.0 and -75.0 <= lon <= -73.0:
            timezone = "America/New_York"
            logger.info(f"Manual mapping detected New York timezone for coordinates ({lat}, {lon})")
            return timezone
        
        # London coordinates: ~51.5074, -0.1278
        if 51.0 <= lat <= 52.0 and -1.0 <= lon <= 0.5:
            timezone = "Europe/London"
            logger.info(f"Manual mapping detected London timezone for coordinates ({lat}, {lon})")
            return timezone
        
        # Tokyo coordinates: ~35.6762, 139.6503
        if 35.0 <= lat <= 36.0 and 139.0 <= lon <= 140.0:
            timezone = "Asia/Tokyo"
            logger.info(f"Manual mapping detected Tokyo timezone for coordinates ({lat}, {lon})")
            return timezone
        
        # If no manual mapping found, try a different API
        try:
            # Use a different timezone API
            response = requests.get(f"https://worldtimeapi.org/api/timezone/Etc/GMT", timeout=5)
            if response.status_code == 200:
                # For now, return UTC as fallback
                logger.warning(f"No timezone mapping found for coordinates ({lat}, {lon}), using UTC")
                return "UTC"
        except Exception as e:
            logger.error(f"Error with fallback API: {e}")
        
        logger.warning(f"No timezone mapping found for coordinates ({lat}, {lon})")
        return None
        
    except Exception as e:
        logger.error(f"Error getting timezone from location for coordinates ({lat}, {lon}): {e}")
        return None

def is_valid_timezone(tz: str) -> bool:
    """Validate timezone string using pytz."""
    import pytz
    return tz in pytz.all_timezones

def get_timezone_display_name(tz: str) -> str:
    """Get a user-friendly display name for a timezone."""
    import pytz
    
    try:
        tz_obj = pytz.timezone(tz)
        now = datetime.now(tz_obj)
        offset = now.strftime('%z')
        offset_formatted = f"{offset[:3]}:{offset[3:]}"
        
        # Extract city name from timezone
        city = tz.split('/')[-1].replace('_', ' ')
        
        return f"{city} (UTC{offset_formatted})"
    except Exception:
        return tz

def convert_utc_to_user_timezone(utc_datetime, user_timezone: str) -> Optional[datetime]:
    """Convert UTC datetime to user's timezone."""
    import pytz
    
    try:
        if not user_timezone or user_timezone == 'UTC':
            return utc_datetime
        
        tz_obj = pytz.timezone(user_timezone)
        if utc_datetime.tzinfo is None:
            utc_datetime = pytz.utc.localize(utc_datetime)
        
        return utc_datetime.astimezone(tz_obj)
    except Exception as e:
        logger.error(f"Error converting UTC to timezone '{user_timezone}': {e}")
        return None

def convert_user_timezone_to_utc(local_datetime, user_timezone: str) -> Optional[datetime]:
    """Convert user's local datetime to UTC."""
    import pytz
    
    try:
        if not user_timezone or user_timezone == 'UTC':
            return local_datetime
        
        tz_obj = pytz.timezone(user_timezone)
        if local_datetime.tzinfo is None:
            local_datetime = tz_obj.localize(local_datetime)
        
        return local_datetime.astimezone(pytz.utc)
    except Exception as e:
        logger.error(f"Error converting timezone '{user_timezone}' to UTC: {e}")
        return None 