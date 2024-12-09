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
logger = logging.getLogger(__name__)
# Set urllib3 logging level to INFO to reduce debug noise
logging.getLogger('urllib3').setLevel(logging.INFO)

dotenv.load_dotenv(override=True)
lat = os.getenv('Coordinates_LAT')
lon = os.getenv('Coordinates_LNG')

radius = 5

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

    def gather_data():
        while True:
            response = requests.get(f"https://api.adsb.one/v2/point/{lat}/{lon}/{radius}")
            data = json.loads(response.text)
            logger.debug(f"Found {len(data['ac'])} flights.")
            with lock:
                for flight in data['ac']:
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
            
            # Then return flights within threshold as before
            return [flight for flight in monitored_flights if flight['last_distance'] <= distance_threshold]

    # Start the data gathering in a separate thread
    threading.Thread(target=gather_data, daemon=True).start()

    return get_flights_within_distance

# Usage
# Call get_flights() to retrieve flights within 3 km

# print (f"curl -X GET 'https://api.adsb.one/v2/point/{lat}/{lon}/{radius}' | jq")
