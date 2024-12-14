#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
from pathlib import Path
import logging
from display_adapter import display_full_refresh, initialize_display, display_cleanup
import time
from datetime import datetime
from weather import WeatherService, draw_weather_display
from bus_service import BusService, update_display
import importlib
import log_config
import random
import traceback
from debug_server import start_debug_server
from wifi_manager import is_connected, no_wifi_loop, get_hostname
from display_adapter import return_display_lock
import threading
import math
from flights import check_flights, gather_flights_within_radius
from threading import Lock

logger = logging.getLogger(__name__)
# Set logging level for PIL.PngImagePlugin and urllib3.connectionpool to warning
logging.getLogger('PIL.PngImagePlugin').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

display_lock = return_display_lock()  # Global lock for display operations

DISPLAY_REFRESH_INTERVAL = int(os.getenv("refresh_interval", 90))
DISPLAY_REFRESH_MINIMAL_TIME = int(os.getenv("refresh_minimal_time", 30))
DISPLAY_REFRESH_FULL_INTERVAL = int(os.getenv("refresh_full_interval", 3600))
WEATHER_UPDATE_INTERVAL = DISPLAY_REFRESH_WEATHER_INTERVAL = int(os.getenv("refresh_weather_interval", 600))

weather_enabled = True if os.getenv("OPENWEATHER_API_KEY") else False

HOTSPOT_ENABLED = os.getenv('hotspot_enabled', 'true').lower() == 'true'
hostname = get_hostname()
HOTSPOT_SSID = os.getenv('hotspot_ssid', f'PiHotspot-{hostname}')
HOTSPOT_PASSWORD = os.getenv('hotspot_password', 'YourPassword')

DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))

COORDINATES_LAT = float(os.getenv('Coordinates_LAT'))
COORDINATES_LNG = float(os.getenv('Coordinates_LNG'))
flights_enabled = True if os.getenv('flights_enabled', 'false').lower() == 'true' else False
aeroapi_enabled = True if os.getenv('aeroapi_enabled', 'false').lower() == 'true' else False
flight_check_interval = int(os.getenv('flight_check_interval', 10))
FLIGHT_MAX_RADIUS = int(os.getenv('flight_max_radius', 3))
flight_altitude_convert_feet = True if os.getenv('flight_altitude_convert_feet', 'false').lower() == 'true' else False

if not weather_enabled:
    logger.warning("Weather is not enabled, weather data will not be displayed. Please set OPENWEATHER_API_KEY in .env to enable it.")

def handle_bus_mode(epd, weather_data, valid_bus_data, error_message, stop_name, current_time):
    """Handle bus display mode updates"""
    in_weather_mode = False
    wait_time = DISPLAY_REFRESH_INTERVAL if not error_message else DISPLAY_REFRESH_MINIMAL_TIME
    
    if weather_enabled:
        update_display(epd, weather_data['current'], valid_bus_data, error_message, stop_name)
    else:
        update_display(epd, None, valid_bus_data, error_message, stop_name)
    
    return in_weather_mode, wait_time

def handle_weather_mode(epd, weather_data, last_weather_data, last_weather_update, current_time):
    """Handle weather display mode updates"""
    in_weather_mode = True
    weather_changed = (
        last_weather_data is None or
        weather_data['current'] != last_weather_data['current'] or
        weather_data['forecast'] != last_weather_data['forecast']
    )
    
    time_since_update = (current_time - last_weather_update).total_seconds()
    
    if (last_weather_data is None or 
        (weather_changed and time_since_update >= WEATHER_UPDATE_INTERVAL) or 
        time_since_update >= 3600):
        
        draw_weather_display(epd, weather_data)
        last_weather_data = weather_data
        last_weather_update = current_time
    
    wait_time = WEATHER_UPDATE_INTERVAL
    return in_weather_mode, wait_time, last_weather_data, last_weather_update

class DisplayManager:
    def __init__(self, epd):
        self.epd = epd
        self.update_count = 0
        self.last_weather_data = None
        self.last_weather_update = datetime.now()
        self.in_weather_mode = False
        self.weather_service = WeatherService() if weather_enabled else None
        self.bus_service = BusService()
        
    def needs_full_refresh(self):
        return self.update_count >= (DISPLAY_REFRESH_FULL_INTERVAL // DISPLAY_REFRESH_INTERVAL)
        
    def perform_full_refresh(self):
        if self.needs_full_refresh():
            logger.info("Performing hourly full refresh...")
            display_full_refresh(self.epd)
            self.update_count = 0
            
    def get_next_update_message(self, wait_time):
        if self.in_weather_mode:
            return f"weather update in {wait_time} seconds"
        updates_until_refresh = (DISPLAY_REFRESH_FULL_INTERVAL // DISPLAY_REFRESH_INTERVAL) - self.update_count - 1
        return f"public transport update in {wait_time} seconds ({updates_until_refresh} until full refresh)"

def initialize_flight_monitoring(epd):
    search_radius = FLIGHT_MAX_RADIUS * 2
    get_flights = gather_flights_within_radius(
        COORDINATES_LAT, 
        COORDINATES_LNG, 
        search_radius, 
        FLIGHT_MAX_RADIUS, 
        flight_check_interval=flight_check_interval,
        aeroapi_enabled=aeroapi_enabled
    )
    flight_thread = threading.Thread(
        target=check_flights,
        args=(epd, get_flights, flight_check_interval),
        daemon=True
    )
    flight_thread.start()

def main():
    epd = None
    try:
        logger.info("E-ink Display Starting")
        start_debug_server()
        epd = initialize_display()
        
        if not is_connected():
            no_wifi_loop(epd)
            
        display_manager = DisplayManager(epd)
        
        if flights_enabled:
            initialize_flight_monitoring(epd)
        
        while True:
            try:
                # Get data
                weather_data = display_manager.weather_service.get_detailed_weather() if weather_enabled else None
                bus_data, error_message, stop_name = display_manager.bus_service.get_waiting_times()
                
                valid_bus_data = [
                    bus for bus in bus_data 
                    if any(time != "--" for time in bus["times"])
                ]
                
                current_time = datetime.now()
                display_manager.perform_full_refresh()
                
                # Update display based on mode
                if valid_bus_data:
                    display_manager.in_weather_mode, wait_time = handle_bus_mode(
                        epd, weather_data, valid_bus_data, error_message, stop_name, current_time
                    )
                    display_manager.update_count += 1
                    display_manager.last_weather_data = None
                    display_manager.last_weather_update = current_time
                elif weather_enabled:
                    (display_manager.in_weather_mode, wait_time, 
                     display_manager.last_weather_data, 
                     display_manager.last_weather_update) = handle_weather_mode(
                        epd, weather_data, display_manager.last_weather_data,
                        display_manager.last_weather_update, current_time
                    )
                
                next_update = display_manager.get_next_update_message(wait_time)
                logger.info(f"Waiting {wait_time} seconds until next update ({next_update})")
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(10)
                continue
                
    except KeyboardInterrupt:
        logger.info("Ctrl+C pressed - Cleaning up...")
    except Exception as e:
        logger.error(f"Main error: {str(e)}\n{traceback.format_exc()}")
    finally:
        logger.info("Cleaning up...")
        if epd is not None:
            try:
                display_cleanup(epd)
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}\n{traceback.format_exc()}")
        sys.exit(0)

if __name__ == "__main__":
    main()
