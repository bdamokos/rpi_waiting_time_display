
from PIL import Image, ImageDraw, ImageFont
import dotenv
import logging
from font_utils import get_font_paths
from display_adapter import return_display_lock
import log_config
import os
import requests
import json
import math
import time
import threading
import requests_cache
from functools import lru_cache
from threading import Event, Lock
logger = logging.getLogger(__name__)


DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))

flight_altitude_convert_feet = True if os.getenv('flight_altitude_convert_feet', 'false').lower() == 'true' else False
display_lock = return_display_lock()

# Initialize requests_cache with specific URLs excluded from caching

requests_cache.install_cache(
    'flight_cache', 
    backend='memory', 
    expire_after=3600,  # Cache expires after 1 hour
    urls_expire_after={
        'https://api.adsb.one/v2/point': 0,  # Do not cache ADS-B API calls
        'https://aeroapi.flightaware.com/aeroapi/account/usage': 0  # Do not cache usage endpoint check
    }
)


# Set urllib3 logging level to INFO to reduce debug noise
logging.getLogger('urllib3').setLevel(logging.INFO)
logging.getLogger('requests_cache').setLevel(logging.INFO)
logging.getLogger('requests_cache.patcher').setLevel(logging.INFO)

dotenv.load_dotenv(override=True)
lat = os.getenv('Coordinates_LAT')
lon = os.getenv('Coordinates_LNG')

radius = int(os.getenv('flight_max_radius', 3))
flight_check_interval = int(os.getenv('flight_check_interval', 10))
aeroapi_enabled = os.getenv("aeroapi_enabled", "false").lower() == "true"
aeroapi_key = os.getenv("aeroapi_key")
aeroapi_enable_paid_usage = os.getenv("aeroapi_enable_paid_usage", "false").lower() == "true"


@lru_cache(maxsize=1024)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1 = float(lat1)
    lon1 = float(lon1)
    lat2 = float(lat2)
    lon2 = float(lon2)
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2) * math.sin(dLat / 2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2) * math.sin(dLon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c / 1000

def gather_flights_within_radius(lat, lon, radius=radius*2, distance_threshold=radius, flight_check_interval=flight_check_interval, aeroapi_enabled=False):
    """Gather flights within radius and return a function to get flights within threshold"""
    monitored_flights = []
    lock = Lock()
    stop_event = Event()  # Create stop_event here
    logger.debug(f"Monitoring flights within {radius}km of {lat}, {lon}, with threshold {distance_threshold} km")
    
    def gather_data():
        last_check_time = 0  # Track last check time
        
        while not stop_event.is_set():
            current_time = time.time()
            
            # Ensure minimum interval between checks
            if current_time - last_check_time < flight_check_interval:
                time.sleep(1)  # Short sleep to prevent CPU spinning
                continue
                
            try:
                response = requests.get(f"https://api.adsb.one/v2/point/{lat}/{lon}/{radius}")
                if response.status_code == 200:
                    data = response.json()
                    logger.debug(f"Found {len(data['ac']) if data and 'ac' in data else 0} flights.")
                    
                    with lock:
                        # Clear old flights that haven't been updated recently
                        current_hex_ids = {flight['hex'] for flight in data.get('ac', [])}
                        monitored_flights[:] = [f for f in monitored_flights if f['hex'] in current_hex_ids]
                        
                        # Update or add new flights
                        for flight in data.get('ac', []):
                            hex_id = flight.get('hex')
                            current_distance = haversine(lat, lon, flight.get('lat'), flight.get('lon'))
                            
                            # Update existing flight or add new one
                            existing_flight = next((f for f in monitored_flights if f['hex'] == hex_id), None)
                            if existing_flight:
                                existing_flight['last_distance'] = current_distance
                            else:
                                monitored_flights.append({
                                    'hex': hex_id,
                                    'last_distance': current_distance,
                                    'callsign': flight.get('flight', '').strip(),
                                    'lat': flight.get('lat', ''),
                                    'lon': flight.get('lon', ''),
                                    'registration': flight.get('r', ''),
                                    'description': flight.get('desc', ''),
                                    'operator': flight.get('ownOp', ''),
                                    'squawk': flight.get('squawk', ''),
                                    'emergency': flight.get('emergency', ''),
                                    'altitude': flight.get('alt_baro', ''),
                                    'heading': flight.get('true_heading', ''),
                                    'last_update': current_time
                                })
                
                last_check_time = current_time
                
            except Exception as e:
                logger.error(f"Error gathering flight data: {e}")
                time.sleep(flight_check_interval)  # Sleep on error
            
            # Sleep for the remaining interval time
            time_to_sleep = max(0, flight_check_interval - (time.time() - current_time))
            if time_to_sleep > 0:
                time.sleep(time_to_sleep)

    def get_flights_within_distance():
        with lock:
            flights_in_range = [f for f in monitored_flights if f['last_distance'] <= distance_threshold]
            if flights_in_range:
                closest_flight = min(flights_in_range, key=lambda x: x['last_distance'])
                logger.debug(f"Closest flight: {closest_flight.get('callsign', 'Unknown')} at {closest_flight['last_distance']:.1f}km")
            return flights_in_range

    # Start the data gathering thread
    gather_thread = threading.Thread(target=gather_data, daemon=True)
    gather_thread.start()

    # Return both the getter function and the stop event
    return get_flights_within_distance

def enhance_flight_data(flight_data):
    '''Enhance flight data with additional information from AeroAPI'''
    logger.debug(f"Enhancing flight data for {flight_data['callsign']}")
    if not flight_data.get('callsign'):
        logger.error(f"No callsign found for {flight_data}")
        return flight_data
    flight_data_enhanced = aeroapi_get_flight(flight_data['callsign'].strip())
    if not flight_data_enhanced:
        logger.error(f"No flight data found for {flight_data['callsign']}")
        return flight_data
    # Add null check for closest_flight_data
    elif flight_data_enhanced:
        # Update operator if not already set
        
        operator_iata = flight_data_enhanced.get('operator_iata', '')
        if operator_iata:
            operator_name = aeroapi_get_operator(operator_iata.strip())
            if operator_name:
                flight_data_enhanced['operator_name'] = operator_name
                logger.debug(f"Operator name set for {flight_data['callsign']}: {operator_name}")

        # Get aircraft type description - add null check
        if flight_data_enhanced.get("aircraft_type"):
            logger.debug(f"Aircraft type set for {flight_data['callsign']}: {flight_data_enhanced['aircraft_type']}")
            manufacturer, type = aeroapi_get_plane_type(flight_data_enhanced["aircraft_type"])
            flight_data_enhanced["manufacturer"] = manufacturer 
            flight_data_enhanced["type"] = type
        if not flight_data_enhanced.get("aircraft_type") and flight_data_enhanced.get("description"):
            flight_data_enhanced["type"] = flight_data_enhanced.get("description")
        elif flight_data_enhanced.get("description"):
                parts = flight_data_enhanced["description"].split(" ", 1)
                if len(parts) == 2:
                    flight_data_enhanced["manufacturer"] = parts[0]
                    flight_data_enhanced["type"] = parts[1]
                else:
                    flight_data_enhanced["type"] = flight_data_enhanced["description"]
        
        # Construct flight number - add null checks
        if flight_data_enhanced.get("operator_iata") and flight_data_enhanced.get("flight_number"):
            flight_data_enhanced["flight_number"] = format_flight_number(
                flight_data_enhanced["operator_iata"],
                flight_data_enhanced["flight_number"]
            )
            logger.debug(f"Flight number set for {flight_data['callsign']}: {flight_data_enhanced['flight_number']}")
        # Update closest flight with new data
        flight_data.update(flight_data_enhanced)

        return flight_data


def format_flight_number(operator_iata, flight_number):
    if operator_iata and flight_number:
        return f"{operator_iata}{flight_number}"
    return None

def _aeroapi_get_data(endpoint, url_params=None, call_params=None):
    api_base_url = "https://aeroapi.flightaware.com/aeroapi"
    headers = {
        "x-apikey": aeroapi_key,
        "Content-Type": "application/json"
    }
    if url_params and call_params:
        response = requests.get(f"{api_base_url}/{endpoint}/{url_params}?{call_params}", headers=headers)
    elif call_params:
        response = requests.get(f"{api_base_url}/{endpoint}?{call_params}", headers=headers)
    elif url_params:
        response = requests.get(f"{api_base_url}/{endpoint}/{url_params}", headers=headers)
    else:
        response = requests.get(f"{api_base_url}/{endpoint}", headers=headers)
    
    if response.status_code == 200:
        
        return response.json()

def aeroapi_get_data(endpoint, url_params=None, call_params=None):
    if not aeroapi_enabled:
        logger.info("AeroAPI is not enabled, please set aeroapi_enabled to true in the .env file")
        return None

    if not aeroapi_key and aeroapi_enabled:
        logger.error("AeroAPI key not found, please set the key in the .env file")
        return None
    if endpoint == "account":
        #logger.debug("Checking AeroAPI usage")
        return _aeroapi_get_data(endpoint, url_params, call_params)
    if aeroapi_get_usage():
        logger.debug(f"Getting data from AeroAPI endpoint: {endpoint}")
        return _aeroapi_get_data(endpoint, url_params, call_params)
aeroapi_usage_data = []

def aeroapi_get_usage():
    global aeroapi_usage_data  # Ensure we are using the global variable
    current_time = time.time()
    last_real_data_time = None
    last_real_data_index = -1

    # Find the last recorded real usage data point
    for index, entry in enumerate(reversed(aeroapi_usage_data)):
        if entry[2] == "real":
            last_real_data_time = entry[0]
            last_real_data_index = len(aeroapi_usage_data) - 1 - index
            break

    # Check if we need to fetch fresh usage data
    if last_real_data_time is None or (current_time - last_real_data_time >= 3600):
        usage_data = aeroapi_get_data("account", "usage")
        if usage_data is not None:
            total_cost = usage_data.get("total_cost", 0)
            # Remove old data before the last real usage data
            if last_real_data_index != -1:
                aeroapi_usage_data = aeroapi_usage_data[last_real_data_index + 1:]
            aeroapi_usage_data.append((current_time, total_cost, "real"))
        else:
            return False

    if aeroapi_usage_data and current_time - aeroapi_usage_data[-1][0] < 3600:
        # Calculate the interpolated cost based on the number of API calls made since the last real data point
        num_api_calls = len(aeroapi_usage_data) - last_real_data_index - 1
        interpolated_cost = aeroapi_usage_data[last_real_data_index][1] + (num_api_calls * 0.01)
        aeroapi_usage_data.append((current_time, interpolated_cost, "interpolated"))
        logger.debug(f"Using interpolated usage cost: {interpolated_cost}")
        if interpolated_cost >= 4.0 and not aeroapi_enable_paid_usage:
            logger.warning(f"Interpolated cost reached 4.0 USD: {interpolated_cost}, blocking further API calls due to uncertainty in cost calculation and to avoid potential charges.")
            return False
        return True

    total_cost = aeroapi_usage_data[-1][1]
    if not aeroapi_enable_paid_usage and total_cost > 4.8:
        logger.warning(f"Total cost exceeds 4.8 USD: {total_cost}, the free quota is 5 USD. Under current settings, further API calls are blocked.")
        return False
    elif aeroapi_enable_paid_usage and total_cost > 4.8:
        logger.warning(f"Total cost exceeds 4.8 USD: {total_cost}, the free quota is 5 USD. Under current settings, further API calls are allowed.")
        logger.info(f"Total cost: {total_cost}")
        return True
    elif total_cost <= 4.8:
        logger.debug(f"AeroAPI total cost: {total_cost}, within free quota.")
        return True
    return False

def aeroapi_get_flight(callsign):
        flight_data = aeroapi_get_data("flights", callsign, "max_pages=1")
        if not flight_data or 'flights' not in flight_data or not flight_data['flights']:
            logger.error(f"No flight data found for {callsign}")
            return None
        if flight_data and 'flights' in flight_data and flight_data['flights']:
            first_flight = flight_data['flights'][0]
            origin = first_flight.get('origin', {}) or {}
            destination = first_flight.get('destination', {}) or {}

            origin_code = origin.get('code_iata', '')
            origin_name = origin.get('name', '')
            origin_city = origin.get('city', '')
            
            destination_code = destination.get('code_iata', '')
            destination_name = destination.get('name', '')
            destination_city = destination.get('city', '')

            type = first_flight.get('type', '')
            
            result = {
                "origin_code": origin_code,
                "origin_name": origin_name,
                "origin_city": origin_city,
                "destination_code": destination_code,
                "destination_name": destination_name,
                "destination_city": destination_city,
                "type": type
            }
            # Add all fields from first_flight to result
            for key, value in first_flight.items():
                if key not in result:  
                    result[key] = value

            return result
        return None
        
def aeroapi_get_operator(operator_code_iata):
    logger.debug(f"Getting operator data for {operator_code_iata}")
    operator_data = aeroapi_get_data("operators", operator_code_iata)
    if operator_data:
        operator_code = operator_data.get('iata', '')
        operator_name = operator_data.get('name', '')

        
        # Check if operators.json exists and read its content
        if os.path.exists('operators.json'):
            with open('operators.json', 'r') as file:
                cached_operators = json.load(file)
        else:
            cached_operators = {}

        # Check if the operator is already cached
        if operator_code in cached_operators:
            return cached_operators[operator_code]

        # Cache the new operator data
        cached_operators[operator_code] = operator_name
        operator_info = {
            "icao": operator_data.get('icao', None),
            "iata": operator_data.get('iata', None),
            "callsign": operator_data.get('callsign', None),
            "name": operator_data.get('name', ''),
            "country": operator_data.get('country', None),
            "location": operator_data.get('location', None),
            "phone": operator_data.get('phone', None),
            "shortname": operator_data.get('shortname', None),
            "url": operator_data.get('url', None),
            "wiki_url": operator_data.get('wiki_url', None),
            "alternatives": []
        }
        
        # Cache the new operator data
        cached_operators[operator_code] = operator_info
        with open('operators.json', 'w') as file:
            json.dump(cached_operators, file)
        logger.debug(f"Operator name set for {operator_code}: {operator_name}")
        return operator_name
    return None


def aeroapi_get_plane_type(aircraft_type):
        if not aircraft_type:
            return None, None

        # Check if types.json exists and read its content
        if os.path.exists('types.json'):
            with open('types.json', 'r') as file:
                cached_types = json.load(file)
        else:
            cached_types = {}

        # Check if the type is already cached
        if aircraft_type in cached_types:
            type_info = cached_types[aircraft_type]
            return type_info['manufacturer'], type_info['type']

        # Get new data from API
        type_data = aeroapi_get_data("aircraft/types", aircraft_type)
        if type_data:
            type_info = {
                "manufacturer": type_data.get('manufacturer', ''),
                "type": type_data.get('type', ''),
                "description": type_data.get('description', ''),
                "engine_count": type_data.get('engine_count', None),
                "engine_type": type_data.get('engine_type', None)
            }
            
            # Cache the new type data
            cached_types[aircraft_type] = type_info
            with open('types.json', 'w') as file:
                json.dump(cached_types, file)

            return type_info['manufacturer'], type_info['type']
        
        return None, None
    

if __name__ == "__main__":
    print("Starting flight monitoring")
    get_flights = gather_flights_within_radius(lat, lon, radius=100, distance_threshold=10)
    time.sleep(5)  # Add a short delay to allow data gathering
    seen_flights = []
    try:
        while True:
            flights = get_flights()
            if flights:
                for flight in flights:
                    existing_flight = next((f for f in seen_flights if f['hex'] == flight['hex']), None)
                    if not existing_flight:
                        aeroapi_result = aeroapi_get_flight(flight['callsign'].strip())
                        if not flight['operator'] and aeroapi_result:
                            operator_iata = aeroapi_result.get('operator_iata', '')
                            if operator_iata:
                                operator_name = aeroapi_get_operator(operator_iata.strip())
                                if operator_name:
                                    flight['operator'] = operator_name
                        if aeroapi_result:
                            flight.update(aeroapi_result)
                        print(f"Flight: {flight['callsign']} ({flight['hex']}) is {flight['last_distance']:.1f}km away. "
                              f"Origin: {flight.get('origin_name', '')} ({flight.get('origin_code', '')}), "
                              f"{flight.get('origin_city', '')}. "
                              f"Destination: {flight.get('destination_name', '')} ({flight.get('destination_code', '')}), "
                              f"{flight.get('destination_city', '')}. "
                              f"Type: {flight.get('type', '')}. "
                              f"Operator: {flight['operator']}. "
                              f"Description: {flight['description']}. ")
                        seen_flights.append(flight)
                    else:
                        previous_distance = existing_flight['last_distance']
                        current_distance = flight['last_distance']
                        if current_distance < previous_distance:
                            print(f"Flight {flight['callsign']} is getting closer: now at {current_distance:.1f} km.")
                        elif current_distance > previous_distance:
                            print(f"Flight {flight['callsign']} is getting farther away: now at {current_distance:.1f} km.")
                        else:
                            print(f"Flight {flight['callsign']} remains at the same distance: {current_distance:.1f} km.")
                        existing_flight.update(flight)
            time.sleep(10)
    except KeyboardInterrupt:
        print("Stopping flight monitoring")


def update_display_with_flights(epd, flights):
    """Update the display with flight information."""
    # Create a new image with mode 'RGB'
    width = epd.height  # Account for rotation
    height = epd.width
    if epd.is_bw_display:
        Himage = Image.new('1', (width, height), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(Himage)

    # Get font paths based on the operating system

    font_paths = get_font_paths()
    # Try to load fonts
    try:
        font_tiny = ImageFont.truetype(font_paths['dejavu'], 10)
        font_small = ImageFont.truetype(font_paths['dejavu'], 12)
        font_medium = ImageFont.truetype(font_paths['dejavu_bold'], 15)
        font_large = ImageFont.truetype(font_paths['dejavu_bold'], 24)
        font_xl = ImageFont.truetype(font_paths['dejavu_bold'], 36)
        emoji_font = ImageFont.truetype(font_paths['emoji'], 16)
        emoji_font_large = ImageFont.truetype(font_paths['emoji'], 20)
        logger.debug(f"Loaded fonts successfully from paths: {font_paths}")
    except IOError as e:
        logger.error(f"Failed to load fonts: {str(e)}")
        font_tiny = font_small = font_medium = font_large = font_xl = emoji_font = emoji_font_large = ImageFont.load_default()

    MARGIN = 8  # Slightly smaller margin
    flight_details = flights[0]

    # Top section: Flight number and operator
    if not flight_details:
        logger.error(f"Flight details not found: {flight_details}")
        return
    operator = flight_details.get('operator_name', '')
    flight_number = flight_details.get('flight_number', '')
    flight_number_font_size = font_small if aeroapi_enabled else font_medium
    if not flight_number:
        flight_number = flight_details.get('registration', '')

    # Draw operator name
    if operator:
        operator_name = operator.get('name', '') if isinstance(operator, dict) else operator
        # Trim operator name if it's too long
        operator_font_size = font_small
        if len(operator_name) > 15:
            operator_font_size = font_tiny
            operator_name = operator_name[:18] + "..."
        draw.text((MARGIN, MARGIN), operator_name, fill='black', font=operator_font_size)
    else:
        callsign = flight_details.get('callsign', " ")
        operator_font_size = font_medium
        draw.text((MARGIN, MARGIN), callsign, fill='black', font=operator_font_size)
    # Draw flight number with plane emoji
    # Split emoji and text to use different fonts
    draw.text((width - 85 - MARGIN, MARGIN), "✈️", fill='black', font=emoji_font)
    draw.text((width - 60 - MARGIN, MARGIN), flight_number, fill='black', font=flight_number_font_size)

    # Draw horizontal line under header
    if aeroapi_enabled:
        draw.line([(MARGIN, 22), (width - MARGIN, 22)], fill='black', width=1)

    # Main section: Origin -> Distance -> Destination
    y_pos = 16  # Moved up even further
    distance_font_size = font_small if aeroapi_enabled else font_medium
    # Draw distance at the top
    distance = f"{flight_details['last_distance']:.1f} km"
    distance_bbox = draw.textbbox((0, 0), distance, font=distance_font_size)
    distance_width = distance_bbox[2] - distance_bbox[0]
    distance_x = (width - distance_width) // 2
    if aeroapi_enabled:
        draw.text((distance_x, MARGIN), distance, fill='black', font=distance_font_size)
    else:
        draw.text((distance_x, height//2 - distance_font_size.size//2-5), distance, fill='black', font=distance_font_size)

    # Origin and Destination (moved up)
    y_pos = y_pos + 10  # Reduced spacing further

    # Origin
    origin_code = flight_details.get('origin_code', '')
    draw.text((MARGIN, y_pos), origin_code, fill='black', font=font_xl)
    # Draw origin city name below the code, but closer
    draw.text((MARGIN, y_pos + font_xl.size+3 ), flight_details.get('origin_city', ''), fill='black', font=font_tiny)

    # Draw arrow
    if flight_details.get('origin_code', '') or flight_details.get('destination_code', ''):
        arrow = "→"
        arrow_bbox = draw.textbbox((0, 0), arrow, font=font_large)
        arrow_width = arrow_bbox[2] - arrow_bbox[0]
        arrow_x = (width - arrow_width) // 2
        draw.text((arrow_x, y_pos + 8), arrow, fill='black', font=font_large)

    # Destination
    dest_code = flight_details.get('destination_code', '')
    dest_city = flight_details.get('destination_city', '')
    dest_bbox = draw.textbbox((0, 0), dest_code, font=font_xl)
    dest_width = dest_bbox[2] - dest_bbox[0]
    dest_x = width - dest_width - MARGIN

    # Draw destination code
    draw.text((dest_x, y_pos), dest_code, fill='black', font=font_xl)
    # Draw destination city name below the code, but closer
    dest_city_bbox = draw.textbbox((0, 0), dest_city, font=font_tiny)
    dest_city_width = dest_city_bbox[2] - dest_bbox[0]
    dest_city_x = width - dest_city_width - MARGIN
    draw.text((dest_city_x, y_pos + font_xl.size+3), dest_city, fill='black', font=font_tiny)

    # Bottom section: Aircraft details
    bottom_y = height - 25  # Moved up slightly

    # Draw horizontal line above bottom section
    draw.line([(MARGIN, bottom_y - 15), (width - MARGIN, bottom_y - 15)], fill='black', width=1)

    # Aircraft type with emoji
    if flight_details.get('type', ''):
        type_length = len(flight_details.get('manufacturer', '')) + len(flight_details.get('type', '')) + 1
    else:
        type_length = len(flight_details.get('description', ''))
    if flight_details.get('type', ''):
        type_text = f"{flight_details.get('manufacturer', '')} {flight_details.get('type', '')}"
    else:
        type_text = f"{flight_details.get('description', '')}"

    if type_length > 15:
        type_text = type_text[:15] + "..."
    draw.text((MARGIN, bottom_y - 3), "🛩️", fill='black', font=emoji_font)
    draw.text((MARGIN + 20, bottom_y - 3), type_text, fill='black', font=font_small)

    # Altitude with emoji
    if flight_details.get('altitude') == "ground":
        draw.text((width - 50 - MARGIN, bottom_y - 3), "On the ground", fill='black', font=font_small)
    else:
        if not flight_altitude_convert_feet:
            alt_text = f"{flight_details.get('altitude', '')} ft"
        else:
            altitude_in_meters = float(flight_details.get('altitude', '')) * 0.3048
            alt_text = f"{altitude_in_meters:.0f} m"
        draw.text((width - 85 - MARGIN, bottom_y - 3), "⛰️", fill='black', font=emoji_font)
        draw.text((width - 60 - MARGIN, bottom_y - 3), alt_text, fill='black', font=font_small)

    # Rotate image for display
    Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)

    # Display the image
    with display_lock:
        buffer = epd.getbuffer(Himage)
        epd.display(buffer)


def check_flights(epd, get_flights, flight_check_interval=10):
    """Check for flights within the set radius and update the display if any are found."""
    while True:
        try:
            flights_within_3km = get_flights()
            if flights_within_3km:
                logger.info(f"Flights within the set radius: {len(flights_within_3km)}")

                closest_flight = flights_within_3km[0]
                # If the closest flight is on the ground, don't show it and get the next one
                if closest_flight.get('altitude') == "ground":
                    logger.debug("Closest flight is on the ground. Looking for next airborne flight.")
                    found_airborne = False
                    for flight in flights_within_3km[1:]:
                        if flight.get('altitude') != "ground":
                            closest_flight = flight
                            found_airborne = True
                            break
                    if not found_airborne:
                        logger.debug("No airborne flights found in the list.")
                        closest_flight = None

                # Enhance the flight data with additional details
                if closest_flight:
                    logger.debug(f"Closest flight: {closest_flight}")
                    enhanced_flight = enhance_flight_data(closest_flight)
                    logger.debug(f"Enhanced flight: {enhanced_flight}")
                    # Update display with the enhanced flight data
                    update_display_with_flights(epd, [enhanced_flight])
            else:
                logger.debug("No flights found within the radius")

            # Always sleep before next check, regardless of whether flights were found
            time.sleep(flight_check_interval)

        except Exception as e:
            logger.error(f"Error in flight check loop: {e}", exc_info=True)
            # Sleep on error to prevent rapid error loops
            time.sleep(flight_check_interval)