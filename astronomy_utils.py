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
    eph = load('de421.bsp')
    
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
    
    # Determine phase name and emoji
    if 0 <= phase_angle < 45:
        name = "New Moon"
        emoji = "🌑"
    elif 45 <= phase_angle < 90:
        name = "Waxing Crescent"
        emoji = "🌒"
    elif 90 <= phase_angle < 135:
        name = "First Quarter"
        emoji = "🌓"
    elif 135 <= phase_angle < 180:
        name = "Waxing Gibbous"
        emoji = "🌔"
    elif 180 <= phase_angle < 225:
        name = "Full Moon"
        emoji = "🌕"
    elif 225 <= phase_angle < 270:
        name = "Waning Gibbous"
        emoji = "🌖"
    elif 270 <= phase_angle < 315:
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

if __name__ == "__main__":
    # Test the function by getting the moon phase and the change over 24 hours
    result = get_daily_moon_change()
    if result:
        print(f"Current moon illumination: {result['current']:.1f}%")
        print(f"Tomorrow's illumination: {result['tomorrow']:.1f}%")
        print(f"Change over 24 hours: {result['change']:+.1f}%")
    print(f"Current moon phase: {get_moon_phase()['name']}, {get_moon_phase()['emoji']}, illumination: {get_moon_phase()['percent_illuminated']:.1f}%")