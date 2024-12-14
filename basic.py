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
from threading import Lock, Event

logger = logging.getLogger(__name__)
# Set logging level for PIL.PngImagePlugin and urllib3.connectionpool to warning
logging.getLogger('PIL.PngImagePlugin').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

display_lock = return_display_lock()  # Global lock for display operations

DISPLAY_REFRESH_INTERVAL = int(os.getenv("refresh_interval", 90))
DISPLAY_REFRESH_MINIMAL_TIME = int(os.getenv("refresh_minimal_time", 30))
DISPLAY_REFRESH_FULL_INTERVAL = int(os.getenv("refresh_full_interval", 3600))
WEATHER_UPDATE_INTERVAL = int(os.getenv("refresh_weather_interval", 600))
BUS_DATA_MAX_AGE = 45  # Consider bus data stale after 30 seconds

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

class WeatherManager:
    def __init__(self):
        self.weather_service = WeatherService() if weather_enabled else None
        self.weather_data = {
            'current': {
                'temperature': '--',
                'description': 'Unknown',
                'humidity': '--',
                'time': datetime.now().strftime('%H:%M'),
                'icon': 'unknown'
            },
            'forecast': [],
            'is_daytime': True,
            'sunrise': '--:--',
            'sunset': '--:--'
        }
        self.last_update = None
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        logger.info("WeatherManager initialized")

    def start(self):
        if weather_enabled and self.weather_service:
            logger.info("Starting weather manager thread...")
            self._thread = threading.Thread(target=self._update_weather, daemon=True)
            self._thread.start()
            logger.info("Weather manager thread started")
            # Get initial weather data
            logger.info("Getting initial weather data...")
            self._update_weather_once()
        else:
            logger.info("Weather manager not started (weather disabled or service unavailable)")

    def _update_weather_once(self):
        """Get weather data once"""
        try:
            if self.weather_service:
                logger.debug("Fetching new weather data...")
                new_data = self.weather_service.get_detailed_weather()
                logger.debug(f"Received weather data: {new_data}")
                
                with self._lock:
                    if new_data:  # Only update if we got valid data
                        self.weather_data = new_data
                        self.last_update = datetime.now()
                        logger.info(f"Weather data updated at {self.last_update.strftime('%H:%M:%S')}")
                        logger.debug(f"Current temperature: {new_data['current']['temperature']}°C")
                    else:
                        logger.warning("Received empty weather data")
        except Exception as e:
            logger.error(f"Error updating weather: {e}")
            logger.debug(traceback.format_exc())

    def _update_weather(self):
        """Weather update loop"""
        logger.info("Weather update loop started")
        while not self._stop_event.is_set():
            try:
                current_time = datetime.now()
                if not self.last_update:
                    logger.debug("No previous update, updating weather now")
                    self._update_weather_once()
                else:
                    time_since_update = (current_time - self.last_update).total_seconds()
                    logger.debug(f"Time since last update: {time_since_update:.1f} seconds")
                    if time_since_update >= WEATHER_UPDATE_INTERVAL:
                        logger.debug("Update interval reached, updating weather")
                        self._update_weather_once()
                    else:
                        logger.debug(f"Next update in {WEATHER_UPDATE_INTERVAL - time_since_update:.1f} seconds")
            except Exception as e:
                logger.error(f"Error in weather update loop: {e}")
                logger.debug(traceback.format_exc())
            
            sleep_time = min(60, WEATHER_UPDATE_INTERVAL)
            logger.debug(f"Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)

    def get_weather(self):
        """Get current weather data"""
        if not weather_enabled:
            logger.debug("Weather is disabled, returning None")
            return None
        with self._lock:
            logger.debug(f"Returning weather data from {self.last_update.strftime('%H:%M:%S') if self.last_update else 'never'}")
            return self.weather_data

    def stop(self):
        if self._thread:
            logger.info("Stopping weather manager thread...")
            self._stop_event.set()
            try:
                self._thread.join(timeout=1.0)
                logger.info("Weather manager thread stopped")
            except TimeoutError:
                logger.warning("Weather thread did not stop cleanly")

class BusManager:
    def __init__(self):
        self.bus_service = BusService()
        self.bus_data = {
            'data': [],
            'error_message': None,
            'stop_name': None
        }
        self.last_update = None
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        logger.info("BusManager initialized")

    def start(self):
        logger.info("Starting bus manager thread...")
        self._thread = threading.Thread(target=self._update_bus_data, daemon=True)
        self._thread.start()
        logger.info("Bus manager thread started")
        # Get initial bus data
        logger.info("Getting initial bus data...")
        self._update_bus_data_once()

    def _update_bus_data_once(self):
        """Get bus data once"""
        try:
            logger.debug("Fetching new bus data...")
            data, error_message, stop_name = self.bus_service.get_waiting_times()
            
            with self._lock:
                self.bus_data = {
                    'data': data,
                    'error_message': error_message,
                    'stop_name': stop_name
                }
                self.last_update = datetime.now()
                logger.info(f"Bus data updated at {self.last_update.strftime('%H:%M:%S')}")
                if data:
                    logger.debug(f"Received {len(data)} bus entries")
                if error_message:
                    logger.warning(f"Bus error message: {error_message}")
        except Exception as e:
            logger.error(f"Error updating bus data: {e}")
            logger.debug(traceback.format_exc())

    def _update_bus_data(self):
        """Bus update loop"""
        logger.info("Bus update loop started")
        while not self._stop_event.is_set():
            try:
                self._update_bus_data_once()
            except Exception as e:
                logger.error(f"Error in bus update loop: {e}")
                logger.debug(traceback.format_exc())
            
            sleep_time = DISPLAY_REFRESH_INTERVAL
            logger.debug(f"Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)

    def get_bus_data(self):
        """Get current bus data"""
        with self._lock:
            current_time = datetime.now()
            if self.last_update is None:
                logger.warning("No bus data has been received yet")
                return [], "Waiting for initial bus data...", None
            
            time_since_update = (current_time - self.last_update).total_seconds()
            if time_since_update > BUS_DATA_MAX_AGE:
                logger.warning(f"Bus data is stale (last update: {time_since_update:.0f} seconds ago)")
                return [], f"Data stale ({time_since_update:.0f}s old)", self.bus_data['stop_name']
            
            logger.debug(f"Returning bus data from {self.last_update.strftime('%H:%M:%S')}")
            return (
                self.bus_data['data'],
                self.bus_data['error_message'],
                self.bus_data['stop_name']
            )

    def stop(self):
        if self._thread:
            logger.info("Stopping bus manager thread...")
            self._stop_event.set()
            try:
                self._thread.join(timeout=1.0)
                logger.info("Bus manager thread stopped")
            except TimeoutError:
                logger.warning("Bus thread did not stop cleanly")

class DisplayManager:
    def __init__(self, epd):
        self.epd = epd
        self.update_count = 0
        self.last_weather_data = None
        self.last_weather_update = datetime.now()
        self.last_display_update = datetime.now()
        self.in_weather_mode = False
        self.weather_manager = WeatherManager()
        self.bus_manager = BusManager()
        self._display_lock = threading.Lock()
        self._check_data_thread = None
        self._stop_event = threading.Event()
        self.min_refresh_interval = int(os.getenv("refresh_minimal_time", 30))
        logger.info(f"DisplayManager initialized with min refresh interval: {self.min_refresh_interval}s")
        
    def start(self):
        logger.info("Starting display manager components...")
        # Start data managers first
        self.weather_manager.start()
        self.bus_manager.start()
        
        # Wait briefly for initial data
        time.sleep(2)
        
        # Force first display update
        self._force_display_update()
        
        # Start the update checker thread
        self._check_data_thread = threading.Thread(target=self._check_display_updates, daemon=True)
        self._check_data_thread.start()
        logger.info("Display manager started - all components running")

    def _force_display_update(self):
        """Force an immediate display update"""
        logger.info("Forcing initial display update...")
        try:
            with self._display_lock:
                bus_data, error_message, stop_name = self.bus_manager.get_bus_data()
                weather_data = self.weather_manager.get_weather()
                
                valid_bus_data = [
                    bus for bus in bus_data 
                    if any(time != "--" for time in bus["times"])
                ]
                
                if valid_bus_data and not error_message:
                    logger.info(f"Initial display: showing bus data ({len(valid_bus_data)} entries)")
                    current_weather = weather_data['current'] if weather_data else None
                    update_display(self.epd, current_weather, valid_bus_data, error_message, stop_name)
                    self.in_weather_mode = False
                elif weather_enabled and weather_data:
                    logger.info("Initial display: showing weather data")
                    draw_weather_display(self.epd, weather_data)
                    self.in_weather_mode = True
                else:
                    logger.warning("No valid data for initial display")
                
                self.last_display_update = datetime.now()
        except Exception as e:
            logger.error(f"Error in initial display update: {e}")
            logger.debug(traceback.format_exc())

    def _can_update_display(self, current_time):
        """Check if enough time has passed since last display update"""
        time_since_last_update = (current_time - self.last_display_update).total_seconds()
        return time_since_last_update >= self.min_refresh_interval

    def _check_display_updates(self):
        """Continuously check for updates and switch modes as needed"""
        logger.info("Starting display update checker thread")
        
        while not self._stop_event.is_set():
            try:
                current_time = datetime.now()
                
                # Only proceed if minimum refresh interval has passed
                if not self._can_update_display(current_time):
                    time.sleep(1)
                    continue
                
                bus_data, error_message, stop_name = self.bus_manager.get_bus_data()
                weather_data = self.weather_manager.get_weather()
                
                valid_bus_data = [
                    bus for bus in bus_data 
                    if any(time != "--" for time in bus["times"])
                ]

                with self._display_lock:
                    time_since_last_update = (current_time - self.last_display_update).total_seconds()
                    
                    if valid_bus_data and not error_message:
                        if self.in_weather_mode or time_since_last_update >= DISPLAY_REFRESH_INTERVAL:
                            logger.info("Updating bus display...")
                            self.in_weather_mode = False
                            self.perform_full_refresh()
                            current_weather = weather_data['current'] if weather_data else None
                            update_display(self.epd, current_weather, valid_bus_data, error_message, stop_name)
                            self.last_display_update = datetime.now()
                            self.update_count += 1
                            logger.info("Bus display updated successfully")
                    elif weather_enabled and weather_data:
                        if (not self.in_weather_mode or 
                            time_since_last_update >= WEATHER_UPDATE_INTERVAL):
                            logger.info("Updating weather display...")
                            self.in_weather_mode = True
                            self.perform_full_refresh()
                            draw_weather_display(self.epd, weather_data)
                            self.last_weather_data = weather_data
                            self.last_weather_update = current_time
                            self.last_display_update = datetime.now()
                            logger.info("Weather display updated successfully")

            except Exception as e:
                logger.error(f"Error in display update checker: {e}")
                logger.debug(traceback.format_exc())

            # Sleep for a short interval but ensure we don't miss our update windows
            time.sleep(1)

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

    def cleanup(self):
        logger.info("Starting display manager cleanup...")
        self._stop_event.set()
        if self._check_data_thread:
            try:
                self._check_data_thread.join(timeout=1.0)
                logger.info("Display checker thread stopped")
            except TimeoutError:
                logger.warning("Display checker thread did not stop cleanly")
        self.weather_manager.stop()
        self.bus_manager.stop()
        logger.info("Display manager cleanup completed")

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
    display_manager = None
    try:
        logger.info("E-ink Display Starting")
        start_debug_server()
        epd = initialize_display()
        
        if not is_connected():
            no_wifi_loop(epd)
            
        display_manager = DisplayManager(epd)
        display_manager.start()
        
        if flights_enabled:
            initialize_flight_monitoring(epd)
        
        # Main loop just keeps the program running and handles interrupts
        while True:
            time.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("Ctrl+C pressed - Cleaning up...")
    except Exception as e:
        logger.error(f"Main error: {str(e)}\n{traceback.format_exc()}")
    finally:
        logger.info("Cleaning up...")
        if display_manager:
            display_manager.cleanup()
        if epd is not None:
            try:
                display_cleanup(epd)
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}\n{traceback.format_exc()}")
        sys.exit(0)

if __name__ == "__main__":
    main()
