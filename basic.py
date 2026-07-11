#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
from pathlib import Path
import logging
from display_adapter import display_full_refresh, initialize_display, display_cleanup
import time
from datetime import datetime, timedelta
from weather.display import WeatherService, draw_weather_display
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
from PIL import Image
from token_display import draw_month_usage, draw_usage_limits
from ynab_budget import (
    YnabBudgetClient,
    configured_views as configured_ynab_views,
    view_at as ynab_view_at,
)
from ynab_display import draw_ynab_view
from token_usage import (
    TokenUsageClient,
    configured_schedule,
    configured_token_views,
    token_view_at,
)
from screen_arbiter import ScreenArbiter
from rss_plugin import RSSPlugin
from calendar_plugin import CalendarPlugin
from display_override_api import DisplayOverrideServer

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

weather_enabled = True if os.getenv("weather_enabled", "true").lower() == "true" else False
transit_enabled = True if os.getenv("transit_enabled", "true").lower() == "true" else False

HOTSPOT_ENABLED = os.getenv('hotspot_enabled', 'true').lower() == 'true'
hostname = get_hostname()
HOTSPOT_SSID = os.getenv('hotspot_ssid', f'PiHotspot-{hostname}')
HOTSPOT_PASSWORD = os.getenv('hotspot_password', 'YourPassword')

DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))

# Default coordinates (Brussels)
DEFAULT_LAT = 50.8503
DEFAULT_LNG = 4.3517

try:
    COORDINATES_LAT = float(os.getenv('Coordinates_LAT', DEFAULT_LAT))
    COORDINATES_LNG = float(os.getenv('Coordinates_LNG', DEFAULT_LNG))
except (ValueError, TypeError):
    logger.warning("Invalid or missing coordinates, using default coordinates (Brussels)")
    COORDINATES_LAT = DEFAULT_LAT
    COORDINATES_LNG = DEFAULT_LNG

flights_enabled = True if os.getenv('flights_enabled', 'false').lower() == 'true' else False
aeroapi_enabled = True if os.getenv('aeroapi_enabled', 'false').lower() == 'true' else False
flight_check_interval = max(1, int(os.getenv('flight_check_interval', 5)))
FLIGHT_MAX_RADIUS = int(os.getenv('flight_max_radius', 3))
flight_altitude_convert_feet = True if os.getenv('flight_altitude_convert_feet', 'false').lower() == 'true' else False

iss_enabled = True if os.getenv('iss_enabled', 'true').lower() == 'true' else False

if not weather_enabled:
    logger.warning("Weather is not enabled, weather data will not be displayed. Please set OPENWEATHER_API_KEY in .env to enable it.")

class WeatherManager:
    def __init__(self):
        self.weather_service = WeatherService() if weather_enabled else None
        # Initialize with a default WeatherData object
        from weather.models import WeatherData, CurrentWeather, WeatherCondition
        self.weather_data = WeatherData(
            current=CurrentWeather(
                temperature=0.0,
                feels_like=0.0,
                humidity=0,
                pressure=0.0,
                condition=WeatherCondition(
                    description="Unknown",
                    icon="unknown"
                )
            ),
            is_day=True
        )
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
                new_data = self.weather_service.get_weather_data()
                logger.debug(f"Received weather data: {new_data}")
                
                # Add detailed logging for sunshine hours
                if new_data and new_data.daily_forecast:
                    logger.info(f"Number of daily forecasts: {len(new_data.daily_forecast)}")
                    for i, forecast in enumerate(new_data.daily_forecast):
                        logger.info(f"Day {i} sunshine duration: {forecast.sunshine_duration}")
                else:
                    logger.warning("No daily forecast data available")
                
                with self._lock:
                    if new_data:  # Only update if we got valid data
                        self.weather_data = new_data
                        self.last_update = datetime.now()
                        logger.info(f"Weather data updated at {self.last_update.strftime('%H:%M:%S')}")
                        logger.debug(f"Current temperature: {new_data.current.temperature}°C")
                        # Log the state after update
                        if self.weather_data.daily_forecast:
                            logger.info(f"Stored sunshine duration: {self.weather_data.daily_forecast[0].sunshine_duration}")
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
                    logger.debug(f"Time since last weatherupdate: {time_since_update:.1f} seconds")
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
        self.bus_service = BusService() if transit_enabled else None
        self.bus_data = {
            'data': [],
            'error_message': None if transit_enabled else "Transit display is disabled",
            'stop_name': None
        }
        self.last_update = None  # Track when we last fetched data
        self._lock = threading.Lock()
        logger.info("BusManager initialized" + (" (disabled)" if not transit_enabled else ""))

    def fetch_data(self):
        """Fetch new bus data on demand"""
        if not transit_enabled:
            return
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
    FLIGHT_SCREEN_OWNER = "flight"
    ISS_SCREEN_OWNER = "iss"
    OVERRIDE_SCREEN_OWNER = "api-override"
    OVERRIDE_MODULE_ALIASES = {
        "bus": "transit",
        "calendar": "calendar",
        "codex": "token",
        "iss": "iss",
        "token": "token",
        "transit": "transit",
        "weather": "weather",
    }

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
        self.prefetch_done = False  # Flag to track if we've prefetched for the next update
        if transit_enabled and self.bus_manager and self.bus_manager.bus_service:
            self.bus_manager.bus_service.set_epd(epd)  # Set the EPD object for the bus service
        self._display_lock = threading.Lock()
        self._prefetch_lock = threading.Lock()  # Add lock for prefetch operations
        self._check_data_thread = None
        self._flight_thread = None
        self._stop_event = threading.Event()
        self.min_refresh_interval = int(os.getenv("refresh_minimal_time", 30))
        self.flight_check_interval = int(os.getenv("flight_check_interval", 10))
        self.flights_enabled = os.getenv("flights_enabled", "false").lower() == "true"
        # Default to Brussels coordinates if not set
        self.coordinates_lat = float(os.getenv('Coordinates_LAT', '50.8503'))
        self.coordinates_lng = float(os.getenv('Coordinates_LNG', '4.3517'))
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
        self.iss_mode_start_time = None
        self.iss_mode_max_seconds = int(os.getenv("iss_mode_max_seconds", "3600"))
        self.flight_screen_priority = int(os.getenv("screen_priority_flight", "50"))
        default_iss_priority = "60" if self.iss_priority else "40"
        self.iss_screen_priority = int(
            os.getenv("screen_priority_iss", default_iss_priority)
        )
        self.screen_arbiter = ScreenArbiter()
        self.override_priority = int(os.getenv("display_override_priority", "30"))
        self.override_duration_seconds = max(
            1, int(os.getenv("display_override_duration_seconds", "300"))
        )
        self._override_module = None
        self._override_generation = 0
        self._override_lock = threading.RLock()
        self._override_render_lock = threading.Lock()
        self._last_screen_owner = None
        self.prefetch_offset = 10  # seconds before display update to fetch new data
        self.display_interval = DISPLAY_REFRESH_INTERVAL
        self.next_update_time = None
        self.next_prefetch_time = None
        self.token_usage_client = TokenUsageClient()
        self.ynab_client = YnabBudgetClient()
        self.display_schedule = configured_schedule()
        self.token_views = configured_token_views()
        self.ynab_views = configured_ynab_views()
        self.current_display_mode = None
        self.current_token_view = None
        self.current_ynab_view = None
        self.calendar_plugin = CalendarPlugin(
            epd,
            self.screen_arbiter,
            self._display_lock,
            on_render=self._calendar_rendered,
        )
        self.override_server = DisplayOverrideServer(
            self.request_display_override,
            self.clear_display_override,
            self.display_override_status,
        )
        self.rss_plugin = RSSPlugin(
            epd,
            self.screen_arbiter,
            self._display_lock,
            on_render=self._plugin_rendered,
        )
        logger.info(f"DisplayManager initialized with min refresh interval: {self.min_refresh_interval}s")
        logger.info(f"DisplayManager initialized with coordinates: {self.coordinates_lat}, {self.coordinates_lng}")
        logger.info(f"DisplayManager initialized with flight mode duration: {self.flight_mode_duration}s")
        logger.info(
            "Screen priorities initialized: flight=%s, iss=%s",
            self.flight_screen_priority,
            self.iss_screen_priority,
        )
        if self.token_usage_client.enabled:
            logger.info("Token usage display enabled with views: %s", ", ".join(self.token_views))
        if self.ynab_client.enabled:
            logger.info("YNAB display enabled with views: %s", ", ".join(self.ynab_views))

    def _calendar_rendered(self, owner):
        self._plugin_rendered(owner)

    def _plugin_rendered(self, owner):
        self.current_display_mode = owner
        self.current_token_view = None
        self.in_weather_mode = False
        self.last_display_update = datetime.now()

    def _scheduled_mode(self, current_time):
        scheduled_mode = self.display_schedule.mode_at(current_time)
        if scheduled_mode in {"ynab", "ynab-always"}:
            if not self.ynab_client.enabled:
                return self._ynab_fallback_mode()
            return (
                scheduled_mode
                if self.ynab_client.get_snapshot()
                else self._ynab_fallback_mode()
            )
        if scheduled_mode not in {"token", "token-always"}:
            return scheduled_mode
        if not self.token_usage_client.enabled:
            return self._token_fallback_mode()
        snapshot = self.token_usage_client.get_snapshot()
        if snapshot and not snapshot.stale and (
            scheduled_mode == "token-always" or snapshot.active
        ):
            return scheduled_mode
        return self._token_fallback_mode()

    @staticmethod
    def _is_token_mode(mode):
        return mode in {"token", "token-always"}

    @staticmethod
    def _is_ynab_mode(mode):
        return mode in {"ynab", "ynab-always"}

    @staticmethod
    def _token_fallback_mode():
        mode = os.getenv("token_usage_fallback_mode", "transit").strip().lower()
        return mode if mode in {"auto", "transit", "weather"} else "transit"

    @staticmethod
    def _ynab_fallback_mode():
        mode = os.getenv("ynab_fallback_mode", "transit").strip().lower()
        return mode if mode in {"auto", "transit", "weather"} else "transit"

    def _draw_token_usage(self, current_time, require_active=True):
        snapshot = self.token_usage_client.get_snapshot()
        if not snapshot or snapshot.stale or (require_active and not snapshot.active):
            return False
        view = token_view_at(current_time, self.token_views)
        set_base_image = self.current_display_mode != "token" or self.current_token_view != view
        if view == "month":
            draw_month_usage(self.epd, snapshot, set_base_image=set_base_image)
        else:
            draw_usage_limits(self.epd, snapshot, set_base_image=set_base_image)
        self.current_display_mode = "token"
        self.current_token_view = view
        self.current_ynab_view = None
        self.in_weather_mode = False
        return True

    def _draw_ynab(self, current_time):
        snapshot = self.ynab_client.get_snapshot()
        if not snapshot:
            return False
        view = ynab_view_at(current_time, self.ynab_views)
        set_base_image = (
            self.current_display_mode != "ynab" or self.current_ynab_view != view
        )
        draw_ynab_view(
            self.epd,
            snapshot,
            view,
            now=current_time,
            set_base_image=set_base_image,
        )
        self.current_display_mode = "ynab"
        self.current_ynab_view = view
        self.current_token_view = None
        self.in_weather_mode = False
        return True

    def request_display_override(self, module):
        requested = module.strip().lower()
        normalized = self.OVERRIDE_MODULE_ALIASES.get(requested)
        if not normalized:
            return {
                "accepted": False,
                "error": "unknown module",
                "modules": sorted(self.OVERRIDE_MODULE_ALIASES),
            }
        with self._override_lock:
            self._override_generation += 1
            generation = self._override_generation
            self._override_module = normalized
            selected = self.screen_arbiter.claim(
                self.OVERRIDE_SCREEN_OWNER,
                self.override_priority,
                self.override_duration_seconds,
            )
        rendered = (
            self._render_display_override(normalized, generation)
            if selected
            else False
        )
        if selected and not rendered:
            released = self._release_failed_override(generation)
            if released:
                self._force_display_update()
        elif selected and rendered:
            with self._override_lock:
                if (
                    generation == self._override_generation
                    and self.screen_arbiter.active_owner()
                    == self.OVERRIDE_SCREEN_OWNER
                ):
                    self._last_screen_owner = self.OVERRIDE_SCREEN_OWNER
        return {
            "accepted": True,
            "module": normalized,
            "duration_seconds": self.override_duration_seconds,
            "rendered": rendered,
            "active_owner": self.screen_arbiter.active_owner(),
        }

    def _release_failed_override(self, generation=None):
        """Drop an active override that could not render its requested view."""

        with self._override_lock:
            if generation is not None and generation != self._override_generation:
                return False
            if self.screen_arbiter.active_owner() != self.OVERRIDE_SCREEN_OWNER:
                return False
            self._override_module = None
            return self.screen_arbiter.release(self.OVERRIDE_SCREEN_OWNER)

    def clear_display_override(self):
        with self._override_lock:
            self._override_generation += 1
            self._override_module = None
            was_active = self.screen_arbiter.release(self.OVERRIDE_SCREEN_OWNER)
        if was_active:
            self._force_display_update()
        return {"cleared": True, "active_owner": self.screen_arbiter.active_owner()}

    def display_override_status(self):
        claim = self.screen_arbiter.claim_for(self.OVERRIDE_SCREEN_OWNER)
        with self._override_lock:
            module = self._override_module if claim else None
        return {
            "module": module,
            "active_owner": self.screen_arbiter.active_owner(),
            "duration_seconds": self.override_duration_seconds,
            "modules": sorted(set(self.OVERRIDE_MODULE_ALIASES.values())),
        }

    def _render_display_override(self, module=None, generation=None):
        with self._override_lock:
            if module is None:
                module = self._override_module
            if generation is None:
                generation = self._override_generation
        with self._override_render_lock:
            with self._override_lock:
                if (
                    generation != self._override_generation
                    or module != self._override_module
                ):
                    return False
            return self._render_display_override_locked(module, generation)

    def _render_display_override_locked(self, module, generation):
        if not module or not self.screen_arbiter.can_render(self.OVERRIDE_SCREEN_OWNER):
            return False
        if module == "calendar":
            return self.calendar_plugin.render_forced_agenda(
                self.OVERRIDE_SCREEN_OWNER
            )
        with self._display_lock:
            with self._override_lock:
                if (
                    generation != self._override_generation
                    or module != self._override_module
                ):
                    return False
            if not self.screen_arbiter.can_render(self.OVERRIDE_SCREEN_OWNER):
                return False
            now = datetime.now()
            if module == "token":
                rendered = self._draw_token_usage(now, require_active=False)
            elif module == "iss":
                from iss import display_next_iss_pass

                next_pass = (
                    self.iss_tracker.next_known_pass(now.timestamp())
                    if self.iss_tracker
                    else None
                )
                display_next_iss_pass(self.epd, next_pass, now=now.astimezone())
                rendered = True
                self.current_display_mode = "iss-prediction"
                self.current_token_view = None
                self.in_weather_mode = False
            elif module == "weather":
                weather_data = self.weather_manager.get_weather_data()
                rendered = bool(weather_enabled and weather_data)
                if rendered:
                    draw_weather_display(self.epd, weather_data, set_base_image=True)
                    self.current_display_mode = "weather"
                    self.current_token_view = None
                    self.in_weather_mode = True
            else:
                bus_data, error_message, stop_name = self.bus_manager.get_bus_data()
                weather_data = self.weather_manager.get_weather_data() if weather_enabled else None
                valid_bus_data = [
                    bus for bus in bus_data
                    if any(value and value != "--" for value in bus["times"])
                ]
                rendered = bool(valid_bus_data and not error_message)
                if rendered:
                    update_display(
                        self.epd,
                        weather_data,
                        valid_bus_data,
                        error_message,
                        stop_name,
                        set_base_image=True,
                    )
                    self.current_display_mode = "transit"
                    self.current_token_view = None
                    self.in_weather_mode = False
            if rendered:
                self.last_display_update = now
            return rendered
        
    def start(self):
        logger.info("Starting display manager components...")
        scheduled_mode = self._scheduled_mode(datetime.now())
        # Token views do not depend on weather. Warm it in the background so a
        # slow provider cannot delay the first scheduled token render.
        if self._is_token_mode(scheduled_mode):
            threading.Thread(
                target=self.weather_manager.start,
                name="WeatherManagerStarter",
                daemon=True,
            ).start()
        else:
            self.weather_manager.start()
        
        # Initialize flight monitoring if enabled
        if self.flights_enabled:
            self.initialize_flight_monitoring()
            logger.info("Flight monitoring initialized")
        
        # Initialize ISS tracking if enabled
        self.initialize_iss_tracking()

        # Calendar events are fetched and rendered independently of the base
        # transit/weather/token data sources.
        self.calendar_plugin.start()
        self.override_server.start()
        self.rss_plugin.start()
        
        # Token views do not depend on transit either. The normal update loop
        # will prefetch it when a transit or automatic window becomes active.
        if not self._is_token_mode(scheduled_mode):
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
        self._flight_thread = threading.Thread(
            target=self._check_flights,
            name="FlightTracker",
            daemon=True
        )
        self._flight_thread.start()

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
            self.in_iss_mode = True
            self.iss_mode_start_time = datetime.now()
            self.screen_arbiter.claim(
                self.ISS_SCREEN_OWNER,
                self.iss_screen_priority,
                self.iss_mode_max_seconds,
            )
            
        def on_pass_end():
            self.in_iss_mode = False
            self.iss_mode_start_time = None
            self.screen_arbiter.release(self.ISS_SCREEN_OWNER)

        def display_position(position):
            if not self.screen_arbiter.can_render(self.ISS_SCREEN_OWNER):
                return False
            from iss import display_iss_info

            with self._display_lock:
                if not self.screen_arbiter.can_render(self.ISS_SCREEN_OWNER):
                    return False
                display_iss_info(self.epd, position)
                self.last_display_update = datetime.now()
                self.current_display_mode = self.ISS_SCREEN_OWNER
            return True

        try:
            self.iss_tracker.run(
                self.epd,
                on_pass_start,
                on_pass_end,
                display_callback=display_position,
            )
        except Exception as e:
            logger.error(f"Error in ISS tracker: {e}")
            self.in_iss_mode = False
            self.iss_mode_start_time = None
            self.screen_arbiter.release(self.ISS_SCREEN_OWNER)

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
                                            self.screen_arbiter.claim(
                                                self.FLIGHT_SCREEN_OWNER,
                                                self.flight_screen_priority,
                                                self.flight_mode_duration,
                                            )
                                            logger.debug(f"Flight mode start time: {self.flight_mode_start}")
                                        else:
                                            logger.debug("Updating flight display while in flight mode")
                                        if self.screen_arbiter.can_render(
                                            self.FLIGHT_SCREEN_OWNER
                                        ):
                                            update_display_with_flights(
                                                self.epd, [enhanced_flight]
                                            )
                                            self.current_display_mode = (
                                                self.FLIGHT_SCREEN_OWNER
                                            )
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
            if not self.screen_arbiter.can_render():
                logger.debug(
                    "Base display update deferred while %s owns the screen",
                    self.screen_arbiter.active_owner(),
                )
                return False
            with self._display_lock:
                if not self.screen_arbiter.can_render():
                    return False
                current_time = datetime.now()
                scheduled_mode = self._scheduled_mode(current_time)
                if self._is_ynab_mode(scheduled_mode) and self._draw_ynab(
                    current_time
                ):
                    self.last_display_update = current_time
                    return True
                if self._is_ynab_mode(scheduled_mode):
                    scheduled_mode = self._ynab_fallback_mode()
                if self._is_token_mode(scheduled_mode) and self._draw_token_usage(
                    current_time, require_active=scheduled_mode == "token"
                ):
                    self.last_display_update = current_time
                    return True
                if self._is_token_mode(scheduled_mode):
                    scheduled_mode = self._token_fallback_mode()
                bus_data, error_message, stop_name = self.bus_manager.get_bus_data()
                weather_data = self.weather_manager.get_weather_data() if weather_enabled else None
                
                valid_bus_data = [
                    bus for bus in bus_data 
                    if any(time and time != "--" and time != "" for time in bus["times"])
                ]
                
                # Check if we have any bus data at all
                if scheduled_mode == "weather" and weather_enabled and weather_data:
                    logger.info("Initial display: scheduled weather mode")
                    draw_weather_display(
                        self.epd,
                        weather_data,
                        set_base_image=self.current_display_mode != "weather",
                    )
                    self.in_weather_mode = True
                    self.current_display_mode = "weather"
                elif not bus_data and not error_message and weather_enabled and weather_data:
                    logger.info("Initial display: no bus data available, showing weather data")
                    if not self.in_weather_mode:
                        # We're switching to weather mode, set base image for partial updates
                        self.in_weather_mode = True
                        draw_weather_display(self.epd, weather_data, set_base_image=True)
                        self.current_display_mode = "weather"
                    else:
                        draw_weather_display(self.epd, weather_data)
                elif valid_bus_data and not error_message:
                    logger.info(f"Initial display: showing bus data ({len(valid_bus_data)} entries)")
                    if self.in_weather_mode:
                        # We're switching from weather mode, set base image for partial updates
                        self.in_weather_mode = False
                        update_display(self.epd, weather_data, valid_bus_data, error_message, stop_name, set_base_image=True)
                        self.current_display_mode = "transit"
                    else:
                        update_display(self.epd, weather_data, valid_bus_data, error_message, stop_name)
                        self.current_display_mode = "transit"
                elif weather_enabled and weather_data:
                    logger.info("Initial display: showing weather data")
                    if not self.in_weather_mode:
                        # We're switching to weather mode, set base image for partial updates
                        self.in_weather_mode = True
                        draw_weather_display(self.epd, weather_data, set_base_image=True)
                        self.current_display_mode = "weather"
                    else:
                        draw_weather_display(self.epd, weather_data)
                        self.current_display_mode = "weather"
                else:
                    logger.warning("No valid data for initial display")
                
                self.last_display_update = datetime.now()
                return True
        except Exception as e:
            logger.error(f"Error in initial display update: {e}")
            logger.debug(traceback.format_exc())
            return False

    def _can_update_display(self, current_time):
        """Check if enough time has passed since last display update"""
        time_since_last_update = (current_time - self.last_display_update).total_seconds()
        return time_since_last_update >= self.min_refresh_interval

    def _schedule_next_update(self):
        """Schedule the next update and prefetch times"""
        current_time = datetime.now()
        self.next_update_time = current_time + timedelta(seconds=self.display_interval)
        if transit_enabled:
            self.next_prefetch_time = self.next_update_time - timedelta(seconds=self.prefetch_offset)
            logger.debug(f"Next prefetch scheduled for {self.next_prefetch_time.strftime('%H:%M:%S')}")
        logger.debug(f"Next update scheduled for {self.next_update_time.strftime('%H:%M:%S')}")

    def _check_display_updates(self):
        """Continuously check for updates and switch modes as needed"""
        self._schedule_next_update()  # Initial schedule
        last_flight_log = 0  # Add this back

        while not self._stop_event.is_set():
            try:
                current_time = datetime.now()

                if self.in_iss_mode and self.iss_mode_start_time:
                    time_in_iss_mode = (
                        current_time - self.iss_mode_start_time
                    ).total_seconds()
                    if time_in_iss_mode >= self.iss_mode_max_seconds:
                        logger.warning(
                            "ISS mode watchdog triggered after %.1fs (max %ss)",
                            time_in_iss_mode,
                            self.iss_mode_max_seconds,
                        )
                        self.in_iss_mode = False
                        self.iss_mode_start_time = None
                        self.screen_arbiter.release(self.ISS_SCREEN_OWNER)

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
                            last_flight_log = 0
                            self.screen_arbiter.release(self.FLIGHT_SCREEN_OWNER)
                            logger.info(f"Starting flight cooldown period of {self.flight_mode_cooldown} seconds")

                active_owner = self.screen_arbiter.active_owner()
                if (
                    active_owner == self.OVERRIDE_SCREEN_OWNER
                    and self._last_screen_owner != self.OVERRIDE_SCREEN_OWNER
                ):
                    with self._override_lock:
                        override_module = self._override_module
                        override_generation = self._override_generation
                    if not self._render_display_override(
                        override_module, override_generation
                    ):
                        self._release_failed_override(override_generation)
                        active_owner = self.screen_arbiter.active_owner()
                if self._last_screen_owner and active_owner is None:
                    self._force_display_update()
                    self._schedule_next_update()
                self._last_screen_owner = active_owner

                # Check if it's time to prefetch data
                if (
                    transit_enabled
                    and not self._is_token_mode(self._scheduled_mode(current_time))
                    and current_time >= self.next_prefetch_time
                ):
                    with self._prefetch_lock:
                        if not self.prefetch_done:  # Check flag under lock
                            logger.debug("Prefetching bus data...")
                            try:
                                self.bus_manager.fetch_data()
                                self.prefetch_done = True
                                logger.debug("Prefetch completed successfully")
                            except Exception as e:
                                logger.error(f"Prefetch failed: {e}")
                                # Don't set prefetch_done to False here - we'll try again next cycle
                                # We want to avoid infinite retry loops within the same cycle

                # Check if it's time to update display
                if (
                    current_time >= self.next_update_time
                    and self.screen_arbiter.can_render()
                ):
                    logger.debug("Updating display...")
                    weather_data = self.weather_manager.get_weather_data() if weather_enabled else None
                    valid_bus_data = self.bus_manager.get_valid_bus_data() if transit_enabled else None
                    error_message = None
                    stop_name = self.bus_manager.get_stop_name() if transit_enabled else None

                    with self._display_lock:
                        if not self.screen_arbiter.can_render():
                            with self._prefetch_lock:
                                self.prefetch_done = False
                            continue
                        scheduled_mode = self._scheduled_mode(current_time)
                        if self._is_ynab_mode(scheduled_mode):
                            if self._draw_ynab(current_time):
                                self.last_display_update = datetime.now()
                                logger.info("YNAB display updated successfully")
                                scheduled_mode = "rendered"
                            else:
                                scheduled_mode = self._ynab_fallback_mode()
                        if self._is_token_mode(scheduled_mode):
                            if self._draw_token_usage(
                                current_time,
                                require_active=scheduled_mode == "token",
                            ):
                                self.last_display_update = datetime.now()
                                logger.info("Token usage display updated successfully")
                                scheduled_mode = "rendered"
                            else:
                                scheduled_mode = self._token_fallback_mode()
                        # Check if we have any bus data at all
                        if scheduled_mode == "rendered":
                            pass
                        elif scheduled_mode == "weather" and weather_enabled and weather_data:
                            logger.info("Updating scheduled weather display...")
                            draw_weather_display(
                                self.epd,
                                weather_data,
                                set_base_image=self.current_display_mode != "weather",
                            )
                            self.in_weather_mode = True
                            self.current_display_mode = "weather"
                            self.last_weather_data = weather_data
                            self.last_weather_update = current_time
                            self.last_display_update = datetime.now()
                        elif not valid_bus_data and not error_message and weather_enabled and weather_data:
                            logger.info("No bus data available, switching to weather mode...")
                            if not self.in_weather_mode:
                                # We're switching to weather mode, set base image for partial updates
                                self.in_weather_mode = True
                                draw_weather_display(self.epd, weather_data, set_base_image=True)
                                self.current_display_mode = "weather"
                            else:
                                draw_weather_display(self.epd, weather_data)
                            self.last_weather_data = weather_data
                            self.last_weather_update = current_time
                            self.last_display_update = datetime.now()
                            logger.info("Weather display updated successfully")
                        elif valid_bus_data and not error_message:
                            logger.info("Updating bus display...")
                            # Pass the full weather data object to update_display
                            if self.in_weather_mode:
                                # We're switching from weather mode, set base image for partial updates
                                self.in_weather_mode = False
                                update_display(self.epd, weather_data, valid_bus_data, error_message, stop_name, set_base_image=True)
                                self.current_display_mode = "transit"
                            else:
                                update_display(
                                    self.epd,
                                    weather_data,
                                    valid_bus_data,
                                    error_message,
                                    stop_name,
                                    set_base_image=self.current_display_mode != "transit",
                                )
                                self.current_display_mode = "transit"
                            self.last_display_update = datetime.now()
                            self.update_count += 1
                            logger.info("Bus display updated successfully")
                        elif weather_enabled and weather_data:
                            logger.info("Updating weather display...")
                            if not self.in_weather_mode:
                                # We're switching to weather mode, set base image for partial updates
                                self.in_weather_mode = True
                                draw_weather_display(self.epd, weather_data, set_base_image=True)
                                self.current_display_mode = "weather"
                            else:
                                draw_weather_display(self.epd, weather_data)
                            self.last_weather_data = weather_data
                            self.last_weather_update = current_time
                            self.last_display_update = datetime.now()
                            logger.info("Weather display updated successfully")

                    # Schedule next update cycle
                    self._schedule_next_update()
                    # Reset prefetch flag for next cycle after display update is complete
                    with self._prefetch_lock:
                        self.prefetch_done = False
                        logger.debug("Reset prefetch flag for next cycle")

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
            # Reinitialize partial mode if supported
            if hasattr(self.epd, 'displayPartial'):
                logger.info("Reinitializing partial mode after full refresh")
                self.epd.init()
                if hasattr(self.epd, 'displayPartBaseImage'):
                    logger.debug("Setting base image for partial updates")
                    # Create a blank base image
                    if self.epd.is_bw_display:
                        base_image = Image.new('1', (self.epd.height, self.epd.width), 1)
                    else:
                        base_image = Image.new('RGB', (self.epd.height, self.epd.width), 'white')
                    base_image = base_image.rotate(DISPLAY_SCREEN_ROTATION, expand=True)
                    self.epd.displayPartBaseImage(self.epd.getbuffer(base_image))

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

        self.override_server.stop()
        self.calendar_plugin.stop()
        self.rss_plugin.stop()
            
        for thread in [self._check_data_thread, self._flight_thread, self._iss_thread]:
            if thread:
                try:
                    thread.join(timeout=1.0)
                    logger.info(f"{thread.name} stopped")
                except TimeoutError:
                    logger.warning(f"{thread.name} did not stop cleanly")
        
        self.weather_manager.stop()
        logger.info("Display manager cleanup completed")

    def exit_flight_mode(self):
        """Handle exiting flight mode and trigger a display update."""
        logger.info("Exiting flight mode")
        self.in_flight_mode = False
        self.flight_mode_start = None
        self.last_flight_mode_end = datetime.now()
        self.screen_arbiter.release(self.FLIGHT_SCREEN_OWNER)

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
