#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
from pathlib import Path
import logging
from display_adapter import display_full_refresh, initialize_display, display_cleanup
import time
from datetime import datetime, timedelta
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
from flights import check_flights, gather_flights_within_radius, update_display_with_flights, enhance_flight_data
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
BUS_DATA_MAX_AGE = max(90, DISPLAY_REFRESH_INTERVAL)  # Ensure bus data doesn't become stale before next refresh

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

iss_enabled = True if os.getenv('iss_enabled', 'true').lower() == 'true' else False

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

    def get_weather_data(self):
        """Return the current weather data with thread safety"""
        with self._lock:
            return self.weather_data

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
        logger.info("BusManager initialized")

    def fetch_data(self):
        """Fetch new bus data on demand"""
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
            
            logger.debug(f"Returning bus data from {self.last_update.strftime('%H:%M:%S')} (age: {time_since_update:.1f}s)")
            return (
                self.bus_data['data'],
                self.bus_data['error_message'],
                self.bus_data['stop_name']
            )

    def get_valid_bus_data(self):
        """Get current bus data if it's valid"""
        data, error_message, stop_name = self.get_bus_data()
        if error_message:
            return None
        return data

    def get_stop_name(self):
        """Get the current stop name"""
        with self._lock:
            return self.bus_data.get('stop_name')

class DisplayManager:
    def __init__(self, epd):
        self.epd = epd
        self.update_count = 0
        self.last_weather_data = None
        self.last_weather_update = datetime.now()
        self.last_display_update = datetime.now()
        self.last_flight_update = datetime.now()
        self.in_weather_mode = False
        self.weather_manager = WeatherManager()
        self.bus_manager = BusManager()
        self.bus_manager.bus_service.set_epd(epd)  # Set the EPD object for the bus service
        self._display_lock = threading.Lock()
        self._check_data_thread = None
        self._flight_thread = None
        self._stop_event = threading.Event()
        self.min_refresh_interval = int(os.getenv("refresh_minimal_time", 30))
        self.flight_check_interval = int(os.getenv("flight_check_interval", 10))
        self.flights_enabled = os.getenv("flights_enabled", "false").lower() == "true"
        self.coordinates_lat = float(os.getenv('Coordinates_LAT'))
        self.coordinates_lng = float(os.getenv('Coordinates_LNG'))
        self.flight_getter = None
        self.in_flight_mode = False
        self.flight_mode_start = None
        self.flight_mode_duration = 30  # Duration in seconds for flight mode
        self.flight_mode_cooldown = 30  # Cooldown period before showing flights again
        self.last_flight_mode_end = None
        self.flight_monitoring_paused = False
        self._flight_lock = threading.Lock()
        self.iss_enabled = os.getenv("iss_enabled", "true").lower() == "true"
        self.iss_priority = os.getenv("iss_priority", "false").lower() == "true"
        self.iss_tracker = None
        self._iss_thread = None
        self.in_iss_mode = False
        self.prefetch_offset = 10  # seconds before display update to fetch new data
        self.display_interval = DISPLAY_REFRESH_INTERVAL
        self.next_update_time = None
        self.next_prefetch_time = None
        logger.info(f"DisplayManager initialized with min refresh interval: {self.min_refresh_interval}s")
        logger.info(f"DisplayManager initialized with coordinates: {self.coordinates_lat}, {self.coordinates_lng}")
        logger.info(f"DisplayManager initialized with flight mode duration: {self.flight_mode_duration}s")
        
    def start(self):
        logger.info("Starting display manager components...")
        # Start weather manager
        self.weather_manager.start()
        
        # Initialize flight monitoring if enabled
        if self.flights_enabled:
            self.initialize_flight_monitoring()
            logger.info("Flight monitoring initialized")
        
        # Initialize ISS tracking if enabled
        self.initialize_iss_tracking()
        
        # Get initial bus data
        self.bus_manager.fetch_data()
        time.sleep(2)
        
        # Force first display update
        self._force_display_update()
        
        # Start the update checker thread
        self._check_data_thread = threading.Thread(target=self._check_display_updates, daemon=True)
        self._check_data_thread.start()
        logger.info("Display manager started - all components running")

    def initialize_flight_monitoring(self):
        """Initialize flight monitoring with cooldown control"""
        search_radius = FLIGHT_MAX_RADIUS * 2
        self.flight_getter = gather_flights_within_radius(
            COORDINATES_LAT, 
            COORDINATES_LNG, 
            search_radius, 
            FLIGHT_MAX_RADIUS, 
            flight_check_interval=flight_check_interval,
            aeroapi_enabled=aeroapi_enabled
        )
        self.flight_thread = threading.Thread(
            target=self._check_flights,
            daemon=True
        )
        self.flight_thread.start()

    def initialize_iss_tracking(self):
        if not self.iss_enabled:
            return
            
        try:
            from iss import ISSTracker
            self.iss_tracker = ISSTracker()
            self._iss_thread = threading.Thread(
                target=self._run_iss_tracker,
                name="ISS_Tracker",
                daemon=True
            )
            self._iss_thread.start()
            logger.info("ISS tracking initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ISS tracking: {e}")
            self.iss_enabled = False

    def _run_iss_tracker(self):
        """Run ISS tracker with display mode management"""
        def on_pass_start():
            if self.iss_priority:
                # Force exit from flight mode if needed
                if self.in_flight_mode:
                    logger.info("ISS pass starting - forcing exit from flight mode")
                    self.in_flight_mode = False
                    self.flight_mode_start = None
            self.in_iss_mode = True
            
        def on_pass_end():
            self.in_iss_mode = False
            self._force_display_update()

        try:
            self.iss_tracker.run(self.epd, on_pass_start, on_pass_end)
        except Exception as e:
            logger.error(f"Error in ISS tracker: {e}")

    def _can_enter_flight_mode(self, current_time):
        """Check if we can enter flight mode based on cooldown"""
        with self._flight_lock:
            if self.last_flight_mode_end is None:
                return True
            cooldown_passed = (current_time - self.last_flight_mode_end).total_seconds() >= self.flight_mode_cooldown
            logger.debug(f"Time since last flight mode: {(current_time - self.last_flight_mode_end).total_seconds():.1f}s, cooldown: {self.flight_mode_cooldown}s")
            return cooldown_passed

    def _check_flights(self):
        """Monitor flights and display when relevant"""
        while not self._stop_event.is_set():
            try:
                current_time = datetime.now()

                # First, check if we're in cooldown
                if not self._can_enter_flight_mode(current_time):
                    logger.debug("In flight cooldown period, skipping flight processing entirely")
                    # Sleep for a longer period during cooldown
                    time.sleep(DISPLAY_REFRESH_MINIMAL_TIME)
                    continue

                # Only check flights if enough time has passed since last check
                if (current_time - self.last_flight_update).total_seconds() >= self.flight_check_interval:
                    if self.flight_getter:
                        flights_within_3km = self.flight_getter()
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
                                
                                with self._display_lock:
                                    with self._flight_lock:
                                        if not self.in_flight_mode:
                                            logger.debug("Entering flight mode")
                                            self.in_flight_mode = True
                                            self.flight_mode_start = current_time
                                            logger.debug(f"Flight mode start time: {self.flight_mode_start}")
                                        else:
                                            logger.debug("Updating flight display while in flight mode")
                                        update_display_with_flights(self.epd, [enhanced_flight])
                                    self.last_display_update = datetime.now()
                                    self.last_flight_update = current_time
                        else:
                            logger.debug("No flights found within the radius")

                # Sleep for the flight check interval
                time.sleep(self.flight_check_interval)

            except Exception as e:
                logger.error(f"Error in flight check loop: {e}")
                logger.debug(traceback.format_exc())
                time.sleep(self.flight_check_interval)

    def _force_display_update(self):
        """Force an immediate display update"""
        logger.info("Forcing initial display update...")
        try:
            with self._display_lock:
                bus_data, error_message, stop_name = self.bus_manager.get_bus_data()
                weather_data = self.weather_manager.get_weather()
                
                valid_bus_data = [
                    bus for bus in bus_data 
                    if any(time and time != "--" for time in bus["times"])
                ]
                
                # Check if we have any bus data at all
                if not bus_data and not error_message and weather_enabled and weather_data:
                    logger.info("Initial display: no bus data available, showing weather data")
                    draw_weather_display(self.epd, weather_data)
                    self.in_weather_mode = True
                elif valid_bus_data and not error_message:
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

    def _schedule_next_update(self):
        """Schedule the next update and prefetch times"""
        current_time = datetime.now()
        self.next_update_time = current_time + timedelta(seconds=self.display_interval)
        self.next_prefetch_time = self.next_update_time - timedelta(seconds=self.prefetch_offset)
        logger.debug(f"Next update scheduled for {self.next_update_time.strftime('%H:%M:%S')}")
        logger.debug(f"Next prefetch scheduled for {self.next_prefetch_time.strftime('%H:%M:%S')}")

    def _check_display_updates(self):
        """Continuously check for updates and switch modes as needed"""
        self._schedule_next_update()  # Initial schedule
        last_flight_log = 0  # Add this back

        while not self._stop_event.is_set():
            try:
                if self.in_iss_mode:
                    # Skip normal updates during ISS passes
                    time.sleep(1)
                    continue
                
                current_time = datetime.now()

                # Handle flight mode checks
                with self._flight_lock:
                    if self.in_flight_mode:
                        time_in_flight_mode = (current_time - self.flight_mode_start).total_seconds()
                        if time_in_flight_mode - last_flight_log >= 5:
                            logger.debug(f"Time in flight mode: {time_in_flight_mode:.1f}s of {self.flight_mode_duration}s")
                            last_flight_log = time_in_flight_mode
                        if time_in_flight_mode >= self.flight_mode_duration:
                            logger.info(f"Exiting flight mode after {time_in_flight_mode:.1f} seconds")
                            self.in_flight_mode = False
                            self.last_flight_mode_end = current_time
                            self.flight_mode_start = None
                            logger.info(f"Starting flight cooldown period of {self.flight_mode_cooldown} seconds")
                            # Force an immediate update to normal display
                            self._force_display_update()
                        time.sleep(1)  # Add sleep when in flight mode
                        continue

                # Check if it's time to prefetch data
                if current_time >= self.next_prefetch_time:
                    logger.debug("Prefetching bus data...")
                    self.bus_manager.fetch_data()

                # Check if it's time to update display
                if current_time >= self.next_update_time:
                    logger.debug("Updating display...")
                    weather_data = self.weather_manager.get_weather_data() if weather_enabled else None
                    valid_bus_data = self.bus_manager.get_valid_bus_data()
                    error_message = None
                    stop_name = self.bus_manager.get_stop_name()

                    with self._display_lock:
                        # Check if we have any bus data at all
                        if not valid_bus_data and not error_message and weather_enabled and weather_data:
                            logger.info("No bus data available, switching to weather mode...")
                            self.in_weather_mode = True
                            self.perform_full_refresh()
                            draw_weather_display(self.epd, weather_data)
                            self.last_weather_data = weather_data
                            self.last_weather_update = current_time
                            self.last_display_update = datetime.now()
                            logger.info("Weather display updated successfully")
                        elif valid_bus_data and not error_message:
                            logger.info("Updating bus display...")
                            self.in_weather_mode = False
                            self.perform_full_refresh()
                            current_weather = weather_data['current'] if weather_data else None
                            update_display(self.epd, current_weather, valid_bus_data, error_message, stop_name)
                            self.last_display_update = datetime.now()
                            self.update_count += 1
                            logger.info("Bus display updated successfully")
                        elif weather_enabled and weather_data:
                            logger.info("Updating weather display...")
                            self.in_weather_mode = True
                            self.perform_full_refresh()
                            draw_weather_display(self.epd, weather_data)
                            self.last_weather_data = weather_data
                            self.last_weather_update = current_time
                            self.last_display_update = datetime.now()
                            logger.info("Weather display updated successfully")

                    # Schedule next update cycle
                    self._schedule_next_update()

            except Exception as e:
                logger.error(f"Error in display update checker: {e}")
                logger.debug(traceback.format_exc())

            # Sleep for a short time to prevent CPU spinning
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
        
        if self.iss_tracker:
            self.iss_tracker.stop()
            
        for thread in [self._check_data_thread, self._flight_thread, self._iss_thread]:
            if thread:
                try:
                    thread.join(timeout=1.0)
                    logger.info(f"{thread.name} stopped")
                except TimeoutError:
                    logger.warning(f"{thread.name} did not stop cleanly")
        
        self.weather_manager.stop()
        logger.info("Display manager cleanup completed")

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
