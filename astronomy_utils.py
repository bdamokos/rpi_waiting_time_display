"""
Utility functions for astronomical calculations using skyfield
"""

from skyfield.api import load
from skyfield.framelib import ecliptic_frame
from datetime import datetime, timezone, timedelta
import logging
import log_config
from functools import lru_cache
logger = logging.getLogger(__name__)

@lru_cache(maxsize=256)
def get_moon_phase(timestamp=None):
    """
    Calculate the current moon phase and return phase information
    
    Args:
        timestamp (datetime, optional): Specific time to calculate phase for. 
                                      Defaults to current time if None.
    
    Returns:
        dict: Dictionary containing:
            - phase_angle (float): Moon phase angle in degrees (0-360)
            - emoji (str): Unicode emoji representing the moon phase
            - name (str): Name of the moon phase
            - percent_illuminated (float): Percentage of moon illuminated
    """
    # Load required ephemeris data
    ts = load.timescale()
    eph = load(get_appropriate_ephemeris())
    
    # Get time
    if timestamp is None:
        t = ts.now()
    else:
        t = ts.from_datetime(timestamp.replace(tzinfo=timezone.utc))
    
    # Get the positions
    sun, moon, earth = eph['sun'], eph['moon'], eph['earth']
    
    # Calculate positions
    e = earth.at(t)
    s = e.observe(sun).apparent()
    m = e.observe(moon).apparent()
    
    # Calculate phase angle using ecliptic longitude
    _, slon, _ = s.frame_latlon(ecliptic_frame)
    _, mlon, _ = m.frame_latlon(ecliptic_frame)
    phase_angle = (mlon.degrees - slon.degrees) % 360.0
    
    # Calculate illumination percentage
    percent = m.fraction_illuminated(sun) * 100
    
    # Determine phase name and emoji with corrected boundaries
    if phase_angle < 22.5:
        name = "New Moon"
        emoji = "🌑"
    elif phase_angle < 67.5:
        name = "Waxing Crescent"
        emoji = "🌒"
    elif phase_angle < 112.5:
        name = "First Quarter"
        emoji = "🌓"
    elif phase_angle < 157.5:
        name = "Waxing Gibbous"
        emoji = "🌔"
    elif phase_angle < 202.5:
        name = "Full Moon"
        emoji = "🌕"
    elif phase_angle < 247.5:
        name = "Waning Gibbous"
        emoji = "🌖"
    elif phase_angle < 292.5:
        name = "Last Quarter"
        emoji = "🌗"
    else: 
        name = "Waning Crescent"
        emoji = "🌘"
    
    return {
        "phase_angle": phase_angle,
        "emoji": emoji,
        "name": name,
        "percent_illuminated": round(percent, 1)
    }

def get_daily_moon_change():
    """Calculate the change in moon illumination over 24 hours"""
    try:
        # Get current time and time 24 hours from now
        now = datetime.now(tz=timezone.utc)
        tomorrow = now + timedelta(days=1)
        
        # Get moon phase for both times
        current_phase = get_moon_phase(now)
        tomorrow_phase = get_moon_phase(tomorrow)
        
        # Calculate the change (as a percentage)
        change = tomorrow_phase['percent_illuminated'] - current_phase['percent_illuminated']
        
        return {
            'current': current_phase['percent_illuminated'],
            'tomorrow': tomorrow_phase['percent_illuminated'],
            'change': change
        }
    except Exception as e:
        logger.error(f"Error calculating moon phase change: {e}")
        return None

def get_appropriate_ephemeris():
    """
    Select the appropriate JPL ephemeris based on the current year.
    
    Returns:
        str: Ephemeris filename to load
        
    Notes:
        - DE421 (1900-2050): Smaller file (~14MB), adequate for basic Earth/Moon/Sun calculations
        - DE440 (1550-2650): Improved accuracy, larger file (~120MB)
        - DE441 (-13000-17000): Extended timespan, very large file (~3GB)
        
        Auto-switching logic:
        - Before 2050: Use DE421 for efficiency (sufficient accuracy, smaller size)
        - 2050-2650: Use DE440 for improved accuracy
        - After 2650: Use DE441 for extended coverage
        
        This ensures the application continues to work accurately far into the future,
        while being efficient with storage space in the present.
    """
    current_year = datetime.now().year
    
    if current_year < 2050:
        return 'de421.bsp'
    elif current_year < 2650:
        return 'de440.bsp'
    else:
        return 'de441.bsp'

if __name__ == "__main__":
    # Test the function by getting the moon phase and the change over 24 hours
    result = get_daily_moon_change()
    if result:
        print(f"Current moon illumination: {result['current']:.1f}%")
        print(f"Tomorrow's illumination: {result['tomorrow']:.1f}%")
        print(f"Change over 24 hours: {result['change']:+.1f}%")
    print(f"Current moon phase: {get_moon_phase()['name']}, {get_moon_phase()['emoji']}, illumination: {get_moon_phase()['percent_illuminated']:.1f}%")