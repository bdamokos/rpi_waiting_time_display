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

def gather_flights_within_radius(lat, lon, radius=10, distance_threshold=3):
    monitored_flights = []
    lock = threading.Lock()
    logger.debug(f"Monitoring flights within {radius}km of {lat}, {lon}, with threshold {distance_threshold} km")
    def gather_data():
        while True:
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
            
            # Log distances of all monitored flights
            for flight in monitored_flights:
                #logger.debug(f"Flight {flight['callsign']} ({flight['hex']}) is {flight['last_distance']:.1f}km away")
                aeroapi_result = aeroapi_get_flight(flight['callsign'].strip())
                if aeroapi_result:
                    
                    print(f"Flight {flight['callsign']} ({flight['hex']}) is {flight['last_distance']:.1f}km away. "
                  f"Origin: {aeroapi_result['origin_name']} ({aeroapi_result['origin_code']}), "
                  f"{aeroapi_result['origin_city']}. "
                  f"Destination: {aeroapi_result['destination_name']} ({aeroapi_result['destination_code']}), "
                  f"{aeroapi_result['destination_city']}. "
                  f"Type: {aeroapi_result['type']}.")
            return [flight for flight in monitored_flights if flight['last_distance'] <= distance_threshold]

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
        logger.debug("Checking AeroAPI usage")
        return _aeroapi_get_data(endpoint, url_params, call_params)
    if aeroapi_get_usage():
        logger.debug(f"Getting data from AeroAPI endpoint: {endpoint}")
        return _aeroapi_get_data(endpoint, url_params, call_params)

def aeroapi_get_usage():
    usage_data = aeroapi_get_data("account", "usage")
    
    if usage_data is not None:
        total_cost = usage_data.get("total_cost", 0)
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

if __name__ == "__main__":
    print("Starting flight monitoring")
    get_flights = gather_flights_within_radius(lat, lon, radius=100, distance_threshold=80)
    time.sleep(5)  # Add a short delay to allow data gathering
    while True:
        flights = get_flights()
        if flights:
            for flight in flights:
                print(f"Flight: {flight['callsign']} ({flight['hex']}) is {flight['last_distance']:.1f}km away")
        else:
            print("No flights within the specified distance threshold.")
        time.sleep(10)