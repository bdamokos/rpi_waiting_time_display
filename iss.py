'''
This is a script to get the ISS position and display it on the screen if it is visible from the user's location


ISS next pass prediction inspired by https://github.com/open-notify/Open-Notify-API and the code at https://github.com/open-notify/Open-Notify-API/blob/master/iss.py

'''

from skyfield.api import load, wgs84
from datetime import datetime, timedelta, timezone
from time import time
import json
import os
import dotenv
import requests
from pathlib import Path
from display_adapter import DisplayAdapter, return_display_lock, initialize_display
from font_utils import get_font_paths
import log_config
import logging
from PIL import Image, ImageDraw, ImageFont
from threading import Event
import humanize
logger = logging.getLogger(__name__)
# Set urllib3 and urllib3.connectionpool log levels to warning
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


dotenv.load_dotenv(override=True)

Coordinates_LAT = os.getenv('Coordinates_LAT')
Coordinates_LNG = os.getenv('Coordinates_LNG')
ISS_ENABLED = os.getenv('ISS_ENABLED', "true") == "true"
ISS_CHECK_INTERVAL = os.getenv('ISS_CHECK_INTERVAL', "600")
display_rotation = int(os.getenv('screen_rotation', 30))


class ISSTracker:
    def __init__(self):
        self.next_passes = []
        self.stop_event = Event()
        self.iss_check_interval = int(os.getenv('ISS_CHECK_INTERVAL', '30'))
        self.prediction_interval = 12 * 3600  # 12 hours in seconds
        self.last_prediction_time = 0
    def calculate_next_passes(self):
        """Calculate next ISS passes and store them"""
        try:
            lat = float(Coordinates_LAT)
            lon = float(Coordinates_LNG)
            
            passes = predict_passes(lat, lon, n=5)
            current_time = time()
            
            # Filter only future passes
            self.next_passes = [
                pass_info for pass_info in passes['response']
                if pass_info['risetime'] > current_time
            ]
            
            if self.next_passes:
                logger.info("Next ISS passes predicted:")
                for pass_info in self.next_passes:
                    logger.info(f"Pass at {pass_info['human_risetime']}, "
                              f"duration: {humanize.precisedelta(timedelta(seconds=pass_info['duration']))}")
            else:
                logger.info("No visible passes predicted in the next period")
                
        except Exception as e:
            logger.error(f"Error calculating passes: {e}")
            self.next_passes = []

    def monitor_pass(self, pass_info, epd):
        """Monitor ISS during a pass window"""
        start_time = pass_info['risetime']
        end_time = start_time + pass_info['duration']
        
        logger.info(f"Starting pass monitoring from {datetime.fromtimestamp(start_time)}")
        
        while time() < end_time and not self.stop_event.is_set():
            is_visible, position = is_iss_near(Coordinates_LAT, Coordinates_LNG, debug=True)
            if position:
                display_iss_info(epd, position)
                logger.debug(f"Updated display with position: {position}")
            
            self.stop_event.wait(self.iss_check_interval)
        
        logger.info(f"Completed pass monitoring at {datetime.now()}")

    def run(self, epd, on_pass_start=None, on_pass_end=None):
        """Main running loop with callbacks"""
        while not self.stop_event.is_set():
            current_time = time()
            
            if current_time - self.last_prediction_time >= self.prediction_interval:
                self.calculate_next_passes()
                self.last_prediction_time = current_time
            
            current_pass = next((pass_info for pass_info in self.next_passes 
                               if current_time < pass_info['risetime'] + pass_info['duration']), None)
            
            if current_pass:
                # If we're in a pass window
                if current_time >= current_pass['risetime']:
                    if on_pass_start:
                        on_pass_start()
                    self.monitor_pass(current_pass, epd)
                    if on_pass_end:
                        on_pass_end()
                else:
                    # Sleep until next pass
                    sleep_time = current_pass['risetime'] - current_time
                    logger.info(f"Sleeping for {humanize.precisedelta(timedelta(seconds=sleep_time))}")
                    self.stop_event.wait(min(sleep_time, 300))
            else:
                # No passes coming up, sleep for a while
                logger.debug("No immediate passes, sleeping for 5 minutes")
                self.stop_event.wait(300)

    def stop(self):
        """Stop the tracker"""
        self.stop_event.set()


def get_iss_position():
    response = requests.get('https://api.wheretheiss.at/v1/satellites/25544')
    return response.json()


def is_iss_near(lat = Coordinates_LAT, lon = Coordinates_LNG, debug=False):
    iss_position = get_iss_position()
    # Get current location coordinates
    lat = float(lat)
    lon = float(lon)
    
    # Check if we're within reasonable distance of ISS position
    iss_lat = float(iss_position['latitude'])
    iss_lon = float(iss_position['longitude'])
    
    # Calculate position data regardless of distance
    ts = load.timescale()
    t = ts.now()
    iss = get_tle_data()
    location = wgs84.latlon(lat, lon)
    difference = iss - location
    topocentric = difference.at(t)
    alt_deg, az_deg, distance = topocentric.altaz()
    
    # Get the next setting event
    t2 = t + timedelta(minutes=20)  # Look ahead 20 minutes
    t_set, events = iss.find_events(location, t, t2, altitude_degrees=10.0)
    set_time = None
    for ti, event in zip(t_set, events):
        if event == 2:  # Setting event
            set_time = ti.utc_datetime()
            break

    position_data = {
        'latitude': iss_lat,
        'longitude': iss_lon,
        'altitude': float(iss_position['altitude']),
        'distance': distance.km,
        'azimuth': az_deg.degrees,
        'elevation': alt_deg.degrees,
        'direction': get_direction(az_deg.degrees),
        'visible_until': set_time,
        'visible_until_human': set_time.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z') if set_time else None
    }
    
    # Rough check if we're within ~2000km viewing radius
    if (abs(iss_lat - lat) > 20 or abs(iss_lon - lon) > 20):
        return False, position_data if debug else None
        
    return True, position_data


def get_tle_data():
    """Get TLE data using skyfield's built-in caching"""
    try:
        satellites = load.tle_file('https://celestrak.org/NORAD/elements/stations.txt')
        return next(sat for sat in satellites if 'ISS' in sat.name)
    except Exception as e:
        logger.error(f"Error loading TLE data: {e}")
        raise

def predict_passes(lat, lon, alt=0, n=5):
    # Load the ISS TLE data
    iss = get_tle_data()
    
    # Create location object
    location = wgs84.latlon(lat, lon, elevation_m=alt)
    
    # Get current time
    ts = load.timescale()
    t0 = ts.from_datetime(datetime.now(tz=timezone.utc))
    
    # Load ephemeris for Sun position
    eph = load('de421.bsp')
    
    # Predict passes
    passes = []
    t = t0
    for _ in range(n):
        # Find the next pass
        t, events = iss.find_events(location, t, t + timedelta(days=1), altitude_degrees=10.0)
        
        # Check if the ISS is sunlit at each event
        sunlit = iss.at(t).is_sunlit(eph)
        
        rise_time = None
        for ti, event, sunlit_flag in zip(t, events, sunlit):
            # Calculate position relative to observer
            difference = iss - location
            topocentric = difference.at(ti)
            alt_deg, az_deg, distance = topocentric.altaz()
            
            if event == 0:  # Rise event
                rise_time = ti.utc_datetime()
                rise_sunlit = sunlit_flag
                rise_alt = alt_deg.degrees
                rise_az = az_deg.degrees
            elif event == 1:  # Maximum elevation
                max_sunlit = sunlit_flag
                max_alt = alt_deg.degrees
                max_az = az_deg.degrees
            elif event == 2:  # Set event
                set_time = ti.utc_datetime()
                set_sunlit = sunlit_flag
                set_alt = alt_deg.degrees
                set_az = az_deg.degrees
                duration = int((set_time - rise_time).total_seconds())
                
                if duration > 60:  # Only include passes longer than 60 seconds
                    passes.append({
                        "risetime": int(rise_time.timestamp()),
                        "human_risetime": rise_time.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'),
                        "duration": duration,
                        "sunlit": {
                            "rise": int(rise_sunlit),
                            "max": int(max_sunlit),
                            "set": int(set_sunlit)
                        },
                        "position": {
                            "rise": {
                                "altitude": round(rise_alt, 2),
                                "azimuth": round(rise_az, 2),
                                "direction": get_direction(rise_az)
                            },
                            "max": {
                                "altitude": round(max_alt, 2),
                                "azimuth": round(max_az, 2),
                                "direction": get_direction(max_az)
                            },
                            "set": {
                                "altitude": round(set_alt, 2),
                                "azimuth": round(set_az, 2),
                                "direction": get_direction(set_az)
                            }
                        }
                    })
                
                # Move time forward for next pass
                t = ti + timedelta(minutes=10)
                break
    
    return {
        "request": {
            "datetime": int(time()),
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "passes": n,
        },
        "response": passes
    }

def get_direction(azimuth):
    """Convert azimuth to cardinal direction"""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = round(azimuth / 22.5) % 16
    return directions[index]


# 🛰️

def display_iss_info(epd, iss_info):
    # Display the ISS info on the screen:
    # Big satellite emoji on the left, some info on the right
    #   ------------------------------
    #   |   🛰️🛰️🛰️           ISS (ZARYA)        |
    #   |   🛰️🛰️🛰️   current lat  lon       |
    #   |   🛰️🛰️🛰️   current altitude       |
    #   |   🛰️🛰️🛰️   current distance       |
    #   |   🛰️🛰️🛰️   current angle, and azimuth  |
    #   |   🛰️🛰️🛰️   visible until              |
    #   ------------------------------
    width = epd.height  # Account for rotation
    height = epd.width
    display_lock = return_display_lock()
    if epd.is_bw_display:
        Himage = Image.new('1', (width, height), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(Himage)

    font_paths = get_font_paths()
    font_tiny = ImageFont.truetype(font_paths['dejavu'], 10)
    font_small = ImageFont.truetype(font_paths['dejavu'], 12)
    font_medium = ImageFont.truetype(font_paths['dejavu_bold'], 12)
    font_large = ImageFont.truetype(font_paths['dejavu_bold'], 16)
    emoji_font = ImageFont.truetype(font_paths['emoji'], 50)

    # Draw satellite emoji on the left
    draw.text((10, 10), "🛰️", font=emoji_font, fill= "black")

    # Draw ISS information on the right
    text_start_x = 70  # Position text to right of emoji
    line_height = 18    # Space between lines
    
    # Line 1: ISS Name
    draw.text((text_start_x, 5), "ISS (ZARYA)", font=font_large, fill="black")
    
    # Line 2: Position
    position_text = f"Position: {iss_info['latitude']:.1f}°, {iss_info['longitude']:.1f}°"
    draw.text((text_start_x, 10 + line_height), position_text, font=font_medium, fill="black")
    
    # Line 3: Altitude
    altitude_text = f"Altitude: {iss_info['altitude']:.1f} km"
    draw.text((text_start_x, 10 + line_height * 2), altitude_text, font=font_medium, fill= "black")
    
    # Line 4: Distance (if available)
    if 'distance' in iss_info:
        distance_text = f"Distance: {iss_info['distance']:.1f} km"
        draw.text((text_start_x, 10 + line_height * 3), distance_text, font=font_medium, fill="black")
    
    # Line 5: Angle and Azimuth
    if 'azimuth' in iss_info:
        direction = get_direction(iss_info['azimuth'])
        angle_text = f"Direction: {direction} ({iss_info['azimuth']:.1f}°)"
        draw.text((text_start_x, 10 + line_height * 4), angle_text, font=font_medium, fill= "black")
    
    # Line 6: Visible until
    if 'visible_until_human' in iss_info and iss_info['visible_until_human'] is not None:
        visible_text = f"Visible until: {iss_info['visible_until_human']}"
        draw.text((text_start_x, 10 + line_height * 5), visible_text, font=font_medium, fill= "black")

    # Rotate and display the image
   
    Himage = Himage.rotate(display_rotation, expand=True)
    with display_lock:
        buffer = epd.getbuffer(Himage)
        epd.display(buffer)


# Example usage
if __name__ == "__main__":
    # # Use your environment variables
    # lat = float(Coordinates_LAT)
    # lon = float(Coordinates_LNG)
    
    # print("Current ISS Position:")
    # print(json.dumps(get_iss_position(), indent=2))
    
    # print("\nISS Position relative to observer:")
    # is_visible, position = is_iss_near(lat, lon, debug=True)
    # print(json.dumps(position, indent=2))
    # print(f"ISS is {'visible' if is_visible else 'not visible'} from your location")
    # epd = initialize_display()

    # display_iss_info(epd, position)

    epd = initialize_display()
    tracker = ISSTracker()
    
    try:
        tracker.run(epd)
    except KeyboardInterrupt:
        logger.info("Stopping ISS tracker")
        tracker.stop()
    except Exception as e:
        logger.error(f"Error in ISS tracker: {e}")
        tracker.stop()