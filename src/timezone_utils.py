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
        4. If you can't determine the timezone, return "UTC"
        
        Examples:
        - "New York" → "America/New_York"
        - "London" → "Europe/London"
        - "Tehran" → "Asia/Tehran"
        - "Tokyo" → "Asia/Tokyo"
        - "Sydney" → "Australia/Sydney"
        
        City: {city_name}
        Timezone:"""
        
        response = model.generate_content(prompt)
        timezone = response.text.strip()
        
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
    """Get timezone from lat/lon using ip-api.com."""
    try:
        response = requests.get(f"http://ip-api.com/json/?lat={lat}&lon={lon}", timeout=5)
        data = response.json()
        if data.get('status') == 'success':
            timezone = data.get('timezone')
            if timezone and is_valid_timezone(timezone):
                logger.info(f"Location API detected timezone '{timezone}' for coordinates ({lat}, {lon})")
                return timezone
    except Exception as e:
        logger.error(f"Error getting timezone from location API for coordinates ({lat}, {lon}): {e}")
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