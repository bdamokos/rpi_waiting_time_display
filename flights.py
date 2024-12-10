#Connect to https://api.adsb.one/v2/point/lat/lon/radius to get flights

import dotenv
import logging
import log_config
import os
import requests
import json
import math
import time
import threading
import requests_cache

# Initialize requests_cache with specific URLs excluded from caching
requests_cache.install_cache(
    'flight_cache', 
    backend='sqlite', 
    expire_after=3600,  # Cache expires after 1 hour
    urls_expire_after={
        'https://api.adsb.one/v2/point': 0,  # Do not cache ADS-B API calls
        'https://aeroapi.flightaware.com/aeroapi/account/usage': 0  # Do not cache usage endpoint check
    }
)

logger = logging.getLogger(__name__)
# Set urllib3 logging level to INFO to reduce debug noise
logging.getLogger('urllib3').setLevel(logging.INFO)
logging.getLogger('requests_cache').setLevel(logging.INFO)
logging.getLogger('requests_cache.patcher').setLevel(logging.INFO)

dotenv.load_dotenv(override=True)
lat = os.getenv('Coordinates_LAT')
lon = os.getenv('Coordinates_LNG')

radius = 5

aeroapi_key = os.getenv("aeroapi_key")
aeroapi_enable_paid_usage = os.getenv("aeroapi_enable_paid_usage", "false").lower() == "true"

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
stop_event = threading.Event()  # Add a threading event to control the thread
def gather_flights_within_radius(lat, lon, radius=10, distance_threshold=3):
    monitored_flights = []
    lock = threading.Lock()
    stop_event = threading.Event()  # Add a threading event to control the thread
    logger.debug(f"Monitoring flights within {radius}km of {lat}, {lon}, with threshold {distance_threshold} km")
    
    def gather_data():
        while not stop_event.is_set():  # Check the event to stop the loop
            response = requests.get(f"https://api.adsb.one/v2/point/{lat}/{lon}/{radius}")
            data = json.loads(response.text) if response.status_code == 200 else {}
            logger.debug(f"Found {len(data['ac']) if data else 0} flights.")
            with lock:
                for flight in data['ac'] if data else []:
                    hex_id = flight.get('hex')
                    current_distance = haversine(lat, lon, flight.get('lat'), flight.get('lon'))
                    
                    if not any(monitored['hex'] == hex_id for monitored in monitored_flights):
                        monitored_flights.append({
                            'hex': hex_id,
                            'last_distance': current_distance,
                            'callsign': flight.get('flight', 'N/A'),
                            'lat': flight.get('lat', 'N/A'),
                            'lon': flight.get('lon', 'N/A'),
                            'registration': flight.get('r', 'N/A'),
                            'description': flight.get('desc', 'N/A'),
                            'operator': flight.get('ownOp', 'N/A'),
                            'squawk': flight.get('squawk', 'N/A'),
                            'emergency': flight.get('emergency', '')
                        })
                    else:
                        for monitored in monitored_flights:
                            if monitored['hex'] == hex_id:
                                monitored['last_distance'] = current_distance
                                break

            time.sleep(10)

    def get_flights_within_distance():
        with lock:
            # First print the closest flight from all monitored flights
            if monitored_flights:
                closest_flight = min(monitored_flights, key=lambda x: x['last_distance'])
                logger.debug(f"Closest flight: {closest_flight['callsign']} at {closest_flight['last_distance']:.1f}km")
            
            # Filter flights within the distance threshold
            flights_within_distance = [flight for flight in monitored_flights if flight['last_distance'] <= distance_threshold]
            
            return flights_within_distance

    # Start the data gathering in a separate thread
    threading.Thread(target=gather_data, daemon=True).start()

    return get_flights_within_distance

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
    if not aeroapi_key:
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
        last_cost = aeroapi_usage_data[-1][1] + 0.01
        aeroapi_usage_data.append((current_time, last_cost, "interpolated"))
        logger.debug(f"Using interpolated usage cost: {last_cost}")
        if last_cost >= 4.0 and not aeroapi_enable_paid_usage:
            logger.warning(f"Interpolated cost reaches 4.0 USD: {last_cost}, blocking further API calls due to uncertainty in cost calculation and to avoid potential charges.")
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
        if flight_data and 'flights' in flight_data and flight_data['flights']:
            first_flight = flight_data['flights'][0]
            origin = first_flight.get('origin', {}) or {}
            destination = first_flight.get('destination', {}) or {}

            origin_code = origin.get('code_iata', 'N/A')
            origin_name = origin.get('name', 'N/A')
            origin_city = origin.get('city', 'N/A')
            
            destination_code = destination.get('code_iata', 'N/A')
            destination_name = destination.get('name', 'N/A')
            destination_city = destination.get('city', 'N/A')

            type = first_flight.get('type', 'N/A')
            
            result = {
                "origin_code": origin_code,
                "origin_name": origin_name,
                "origin_city": origin_city,
                "destination_code": destination_code,
                "destination_name": destination_name,
                "destination_city": destination_city,
                "type": type
            }
            return result
        else:
            return None
        
def aeroapi_get_operator(operator_code_iata):
    operator_data = aeroapi_get_data("operators", operator_code_iata)
    if operator_data:
        operator_code = operator_data.get('iata', '')
        operator_name = operator_data.get('name', '')

        
        # Check if operators.js exists and read its content
        if os.path.exists('operators.js'):
            with open('operators.js', 'r') as file:
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
        with open('operators.js', 'w') as file:
            json.dump(cached_operators, file)

        return operator_name
    return None

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
                    if flight not in seen_flights:
                        aeroapi_result = aeroapi_get_flight(flight['callsign'].strip())
                        if not flight['operator'] and aeroapi_result:
                            operator_iata = aeroapi_result.get('operator_iata', '').strip()
                            if operator_iata:
                                operator_name = aeroapi_get_operator(operator_iata)
                                if operator_name:
                                    flight['operator'] = operator_name
                        if aeroapi_result:
                            flight.update(aeroapi_result)
                        print(f"Flight: {flight['callsign']} ({flight['hex']}) is {flight['last_distance']:.1f}km away. "
                              f"Origin: {flight.get('origin_name', 'N/A')} ({flight.get('origin_code', 'N/A')}), "
                              f"{flight.get('origin_city', 'N/A')}. "
                              f"Destination: {flight.get('destination_name', 'N/A')} ({flight.get('destination_code', 'N/A')}), "
                              f"{flight.get('destination_city', 'N/A')}. "
                              f"Type: {flight.get('type', 'N/A')}. "
                              f"Operator: {flight['operator']}. "
                              f"Description: {flight['description']}. ")
                        seen_flights.append(flight)
            time.sleep(10)
    except KeyboardInterrupt:
        stop_event.set()  # Set the event to stop the thread
        print("Stopping flight monitoring")