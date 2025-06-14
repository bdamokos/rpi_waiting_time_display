from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import niquests as requests
import logging
from typing import List, Dict, Tuple
import os
import dotenv
from dithering import draw_dithered_box, draw_multicolor_dither_with_text
from color_utils import find_optimal_colors
from font_utils import get_font_paths
import log_config
import socket
from display_adapter import DisplayAdapter, return_display_lock
from functools import lru_cache
from threading import Event
from backoff import ExponentialBackoff
from weather.display import load_svg_icon
from weather.models import WeatherData, TemperatureUnit
from weather.icons import ICONS_DIR
import traceback
import json
from pathlib import Path
import threading
import time

logger = logging.getLogger(__name__)

dotenv.load_dotenv(override=True)


fallback_to_schedule = os.getenv("fallback_to_schedule", "false").lower() == "true"


def _get_stop_config():
    """
    Get stop configuration from environment variables.
    Handles both 'Stops' and 'Stop' variables for backward compatibility.
    Case-insensitive: accepts any variation like STOP, stop, Stops, STOPS, etc.
    Also accepts variants with a period like 'stop.'
    """
    # Get all environment variables
    env_vars = dict(os.environ)
    
    # Try to find any variation of 'stops' first
    stops_pattern = 'stops'
    for key in env_vars:
        if key.lower().rstrip('.') == stops_pattern:
            return env_vars[key]
    
    # If not found, try to find any variation of 'stop'
    stop_pattern = 'stop'
    for key in env_vars:
        if key.lower().rstrip('.') == stop_pattern:
            logger.warning(f"Using '{key}' instead of 'Stops' in .env file. Please update your configuration to use 'Stops' for consistency.")
            return env_vars[key]
    
    return None

show_sunshine = os.getenv('show_sunshine_hours', 'true').lower() == 'true'
show_precipitation = os.getenv('show_precipitation', 'true').lower() == 'true'
Stop = _get_stop_config()
Lines = os.getenv("Lines", "")  # Default to empty string instead of None
bus_api_base_url = os.getenv("BUS_API_BASE_URL", "http://localhost:5001/")
bus_schedule_url = os.getenv("BUS_SCHEDULE_URL", bus_api_base_url)
pre_load_bus_schedule = os.getenv("PRE_LOAD_BUS_SCHEDULE", "false").lower() == "true"
bus_provider = os.getenv("Provider", "stib")
logging.debug(f"Bus provider: {bus_provider}. Base URL: {bus_api_base_url}. Monitoring lines: {Lines if Lines else 'all'} and stop: {Stop}")

DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))
weather_enabled = True if os.getenv("weather_enabled", "true").lower() == "true" else False
display_lock = return_display_lock() # Global lock for display operations
# Define our available colors and their RGB values
DISPLAY_COLORS = {
    'black': (0, 0, 0),
    'white': (255, 255, 255),
    'red': (255, 0, 0),
    'yellow': (255, 255, 0)
}

def _parse_lines(lines_str: str) -> list:
    """
    Parse bus line numbers from environment variable.
    Handles different formats:
    - Single number: "64"
    - Comma-separated list: "64,59"
    - Space-separated list: "64 59"
    - Mixed format: "64, 59"
    - List format: [59, 64]
    - String list format: ["59", "64"]
    - Preserves leading zeros: "0090" stays "0090"
    - Empty string or None: returns empty list (all lines will be shown)
    """
    if not lines_str:
        logger.info("No specific bus lines configured, will show all available lines")
        return []
    
    # Remove leading/trailing whitespace
    lines_str = lines_str.strip()
    
    # Handle list-like formats
    if lines_str.startswith('[') and lines_str.endswith(']'):
        # Remove brackets and split
        content = lines_str[1:-1].strip()
        # Handle empty list
        if not content:
            return []
        # Split on comma and handle quotes
        items = [item.strip().strip('"\'') for item in content.split(',')]
        try:
            # Verify each item is a valid number but return original string
            for item in items:
                int(item)  # Just to validate it's a number
            return items
        except ValueError as e:
            logger.error(f"Invalid number in list format: {e}")
            return []
    
    try:
        # Try to parse as a single number (validate but preserve format)
        int(lines_str)  # Just to validate it's a number
        return [lines_str]
    except ValueError:
        # If that fails, try to split and parse as list
        # First replace commas with spaces
        cleaned = lines_str.replace(',', ' ')
        # Split on whitespace and filter out empty strings
        cleaned = [x.strip() for x in cleaned.split() if x.strip()]
        
        # Validate numbers but preserve original format
        try:
            for line in cleaned:
                int(line)  # Just to validate it's a number
            return cleaned
        except ValueError as e:
            logger.error(f"Invalid bus line number format: {e}")
            return []

class BusService:
    def __init__(self):
        self.base_url = self._resolve_base_url()
        self.schedule_url = self._resolve_schedule_url()
        self.provider = os.getenv("Provider", "stib")
        self.current_provider = self.provider  # Keep track of current active provider
        self.provider_config = self._load_provider_config()
        logger.debug(f"Bus provider: {self.provider}. Resolved Base URL: {self.base_url}")
        self._update_api_urls()
        self.stop_id = Stop
        logger.debug(f"Stop ID: {self.stop_id}")
        self.lines_of_interest = _parse_lines(Lines)
        logger.info(f"Monitoring bus lines: {self.lines_of_interest}")
        # Initialize separate backoffs for RT and fallback
        self._rt_backoff = ExponentialBackoff(initial_backoff=180, max_backoff=3600)
        self._fallback_backoff = ExponentialBackoff(initial_backoff=180, max_backoff=3600)
        self._stop_event = Event()
        self.epd = None  # Will be set later
        
        # Start health check and pre-warming thread
        self._start_health_check()

    def _resolve_base_url(self) -> str:
        """Resolve the base URL, handling .local domains"""
        base_url = bus_api_base_url.lower().rstrip('/')
        if '.local' in base_url:
            try:
                # Extract hostname from URL
                hostname = base_url.split('://')[1].split(':')[0]
                # Try to resolve the IP address
                ip = socket.gethostbyname(hostname)
                logger.info(f"Resolved {hostname} to {ip}")
                # Replace hostname with IP in URL
                return base_url.replace(hostname, ip)
            except Exception as e:
                logger.warning(f"Could not resolve {hostname}, falling back to IP: {e}")
                # Fallback to direct IP if resolution fails
                return "http://127.0.0.1:5001"
        return base_url
    
    def _resolve_schedule_url(self) -> str:
        """Resolve the schedule URL, handling .local domains"""
        schedule_url = bus_schedule_url.lower().rstrip('/')
        if '.local' in schedule_url:
            try:
                # Extract hostname from URL
                hostname = schedule_url.split('://')[1].split(':')[0]
                # Try to resolve the IP address
                ip = socket.gethostbyname(hostname)
                logger.info(f"Resolved {hostname} to {ip}")
                # Replace hostname with IP in URL
                return schedule_url.replace(hostname, ip)
            except Exception as e:
                logger.warning(f"Could not resolve {hostname}, falling back to IP: {e}")
                # Fallback to direct IP if resolution fails
                return "http://127.0.0.1:5001"
        return schedule_url

    def _start_health_check(self):
        """Start a thread to check API health and pre-warm schedule provider"""
        def health_check_task():
            # First, wait for the API to be healthy
            while not self._stop_event.is_set():
                try:
                    logger.info("Checking API health...")
                    response = requests.get(f"{self.base_url}/health", timeout=10)
                    if response.status_code == 200:
                        logger.info("API is healthy")
                        break
                except Exception as e:
                        logger.warning(f"API health check failed: {e}")
                        time.sleep(10)  # Wait 10 seconds before next attempt

            # If pre-load is enabled and we have a schedule provider, start pre-warming
            if pre_load_bus_schedule and self._get_provider_type(self.provider) == 'realtime':
                fallback = self._get_fallback_provider()
                if fallback:
                    try:
                        logger.info(f"Pre-warming schedule provider {fallback}")
                        # Send request directly to schedule URL
                        response = requests.get(
                            f"{self.schedule_url}/api/{fallback}/waiting_times",
                            params={"stop_id": self.stop_id, "download": "true"},
                            timeout=300  # 5 minute timeout for initial load
                        )
                        if response.status_code == 200:
                            logger.info(f"Successfully pre-warmed schedule provider {fallback}")
                        else:
                            logger.warning(f"Pre-warm returned status {response.status_code}: {response.text}")
                    except Exception as e:
                                    logger.warning(f"Failed to pre-warm schedule provider: {e}")

        # Start health check in background thread
        thread = threading.Thread(target=health_check_task, name="APIHealthCheck")
        thread.daemon = True  # Make thread exit when main program exits
        thread.start()
        logger.debug("Started API health check thread")

    def _load_provider_config(self) -> dict:
        """Load provider configuration from JSON file"""
        try:
            config_path = Path(__file__).parent / 'docs/setup/js/providers.json'
            with open(config_path, 'r') as f:
                config = json.load(f)
            return config
        except Exception as e:
            logger.error(f"Failed to load provider config: {e}")
            return {"providers": []}
            
    def _get_provider_type(self, provider_id: str) -> str:
        """
        Determine if a provider is realtime, schedule-only, or unknown
        Returns: 'realtime', 'schedule', or 'unknown'
        """
        try:
            for provider in self.provider_config.get('providers', []):
                if provider.get('realtime_provider') == provider_id:
                    return 'realtime'
                if provider.get('schedule_provider') == provider_id:
                    return 'schedule'
            return 'unknown'
        except Exception as e:
            logger.error(f"Error determining provider type: {e}")
            return 'unknown'

    def _get_fallback_provider(self) -> str:
        """Get fallback provider for current provider"""
        try:
            # If current provider is already a schedule provider or unknown, no fallback
            provider_type = self._get_provider_type(self.provider)
            if provider_type in ['schedule', 'unknown']:
                logger.info(f"Provider {self.provider} is {provider_type}, no fallback needed")
                return None

            # Look for fallback for realtime provider
            for provider in self.provider_config.get('providers', []):
                if provider.get('realtime_provider') == self.provider:
                    return provider.get('schedule_provider')
            return None
        except Exception as e:
            logger.error(f"Error getting fallback provider: {e}")
            return None
            
    def _update_api_urls(self):
        """Update API URLs based on current provider"""
        base = self.schedule_url if self._get_provider_type(self.current_provider) == 'schedule' else self.base_url
        # Remove trailing slashes from base URL and ensure single slashes in path
        base = base.rstrip('/')
        self.api_url = f"{base}/api/{self.current_provider}/waiting_times?stop_id={Stop}&download=true"
        self.colors_url = f"{base}/api/{self.current_provider}/colors"
        logger.debug(f"Updated URLs - API: {self.api_url}, Colors: {self.colors_url}")

    def _try_realtime_provider(self) -> tuple[bool, dict]:
        """Try to fetch data from realtime provider"""
        # Only try RT if we're using a known RT provider
        if self._get_provider_type(self.provider) != 'realtime':
            logger.debug(f"Provider {self.provider} is not a realtime provider, skipping RT check")
            return False, None

        if not self._rt_backoff.should_retry():
            return False, None

        try:
            # Temporarily switch URLs to RT provider
            original_urls = (self.api_url, self.colors_url)
            self.current_provider = self.provider
            self._update_api_urls()

            response = requests.get(self.api_url, timeout=120)
            data = response.json()
            
            # Update backoff state
            self._rt_backoff.update_backoff_state(True)
            return True, data
        except requests.exceptions.ConnectionError as e:
            logger.debug(f"Realtime provider connection error: {e}")
            self._rt_backoff.update_backoff_state(False, error_type='connection')
            # Restore URLs if we're staying with fallback
            self.api_url, self.colors_url = original_urls
            return False, None
        except requests.exceptions.Timeout as e:
            logger.debug(f"Realtime provider timeout: {e}")
            self._rt_backoff.update_backoff_state(False, error_type='timeout')
            # Restore URLs if we're staying with fallback
            self.api_url, self.colors_url = original_urls
            return False, None
        except Exception as e:
            logger.debug(f"Realtime provider error: {e}")
            self._rt_backoff.update_backoff_state(False, error_type='error')
            # Restore URLs if we're staying with fallback
            self.api_url, self.colors_url = original_urls
            return False, None

    def _check_schedule_health(self) -> bool:
        """Check if schedule provider is healthy"""
        try:
            fallback = self._get_fallback_provider()
            if not fallback:
                logger.warning("No fallback provider configured")
                return False
            logger.info(f"Checking schedule health for provider {fallback}")
            response = requests.get(f"{self.schedule_url}/health", timeout=10)
            logger.info(f"Schedule health check response: {response.status_code}")
            if response.status_code != 200:
                logger.warning(f"Schedule health check failed with status {response.status_code}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Schedule health check failed: {e}")
            return False

    def get_waiting_times(self) -> tuple[List[Dict], str, str]:
        """Fetch and process waiting times for our bus lines"""
        # Only check RT if we started with a RT provider
        if self.current_provider != self.provider and self._get_provider_type(self.provider) == 'realtime':
            logger.info(f"Attempting to switch back to realtime provider {self.provider}")
            success, rt_data = self._try_realtime_provider()
            if success:
                logger.info("Successfully switched back to realtime provider")
                return self._process_response_data(rt_data)
            else:
                logger.warning("Failed to switch back to realtime provider")

        # Get current backoff based on provider type
        provider_type = self._get_provider_type(self.current_provider)
        current_backoff = self._rt_backoff if provider_type == 'realtime' else self._fallback_backoff
        logger.debug(f"Current provider: {self.current_provider}, type: {provider_type}")

        if not current_backoff.should_retry():
            # Only try fallback if we're a RT provider
            if provider_type == 'realtime' and fallback_to_schedule:
                fallback = self._get_fallback_provider()
                if fallback and self._check_schedule_health():
                    logger.info(f"Switching to fallback provider: {fallback}")
                    self.current_provider = fallback
                    self._update_api_urls()
                    # Only retry fallback if it's not in backoff
                    if self._fallback_backoff.should_retry():
                        return self.get_waiting_times()
                    else:
                        logger.warning("Fallback provider is in backoff state")
            error_type = current_backoff.get_last_error()
            error_msg = {
                'connection': "Unable to connect to service",
                'timeout': "Service not responding",
                None: "Service temporarily unavailable"
            }.get(error_type, "Service temporarily unavailable")
            return self._get_error_data(), f"{error_msg}. Next attempt at {current_backoff.get_retry_time_str()}", ""

        try:
            logger.info(f"Fetching waiting times from {self.api_url}")
            response = requests.get(self.api_url, timeout=120)
            logger.debug(f"API response time: {response.elapsed.total_seconds():.3f} seconds")
            logger.debug(f"API response status: {response.status_code}")
            if response.status_code != 200:
                logger.warning(f"API response text: {response.text}")
            response.raise_for_status()
            data = response.json()
            
            # Update appropriate backoff on success
            if provider_type == 'realtime':
                self._rt_backoff.update_backoff_state(True)
            else:
                self._fallback_backoff.update_backoff_state(True)
            
            return self._process_response_data(data)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if provider_type == 'realtime':
                self._rt_backoff.update_backoff_state(False, error_type='connection' if isinstance(e, requests.exceptions.ConnectionError) else 'timeout')
            else:
                self._fallback_backoff.update_backoff_state(False, error_type='connection' if isinstance(e, requests.exceptions.ConnectionError) else 'timeout')
            return self._get_error_data(), "Connection failed" if isinstance(e, requests.exceptions.ConnectionError) else "Service not responding", ""
        except Exception as e:
            if provider_type == 'realtime':
                self._rt_backoff.update_backoff_state(False, error_type='error')
            else:
                self._fallback_backoff.update_backoff_state(False, error_type='error')
            # If using realtime provider and failed, try fallback
            if self.current_provider == self.provider:
                fallback = self._get_fallback_provider()
                if fallback:
                    logger.info(f"Error with realtime provider, switching to fallback: {fallback}")
                    self.current_provider = fallback
                    self._update_api_urls()
                    self._fallback_backoff.reset()  # Reset backoff for fallback provider
                    return self.get_waiting_times()  # Retry with fallback
            logger.error(f"Error fetching bus times: {e}", exc_info=True)
            return self._get_error_data(), "Service error", ""

    def _process_response_data(self, data: dict) -> tuple[List[Dict], str, str]:
        """Process the response data into waiting times format"""
        try:
            # Get provider type once at the start
            provider_type = self._get_provider_type(self.current_provider)
            
            stops_data_location_keys = ['stops_data', 'stops']
            for key in stops_data_location_keys:
                if key in data:
                    stop_data = data[key].get(self.stop_id, {})
                    # Debug print all stop IDs found
                    all_stop_ids = list(data[key].keys())
                    logger.debug(f"All stop IDs found in response: {all_stop_ids}")
                    logger.debug(f"Looking for target stop ID: {self.stop_id}")
                    logger.debug(f"Target stop ID found: {self.stop_id in all_stop_ids}")
                    break

            # Extract waiting times for our stop
            if not stop_data:
                logger.error(f"Stop '{self.stop_id}' not found in response, as no stop data was found")
                return self._get_error_data(), "Stop data not found", ""

            # Get stop name
            stop_name = stop_data.get("name", "")
            logger.debug(f"Stop name: {stop_name}")

            # Check if there are any lines in the stop data
            if not stop_data.get("lines"):
                logger.info(f"No active lines at stop {stop_name}")
                return [], None, stop_name

            bus_times = []
            # If no specific lines are configured, use all lines from the stop data
            lines_to_process = self.lines_of_interest if self.lines_of_interest else stop_data.get("lines", {}).keys()
            for line in lines_to_process:
                logger.debug(f"Processing line {line}")
                line_data = stop_data.get("lines", {}).get(line, {})
                logger.debug(f"Line data found: {line_data}")
                
                if not line_data:
                    logger.warning(f"No data found for line {line}")
                    continue

                # Get line display name from metadata if available
                display_line = line  # Default to route ID
                if '_metadata' in line_data:
                    metadata = line_data['_metadata']
                    if isinstance(metadata, list) and len(metadata) > 0:
                        # New format: array of metadata objects
                        metadata = metadata[0]  # Take first metadata entry
                        if 'route_short_name' in metadata:
                            display_line = metadata['route_short_name']
                            logger.debug(f"Using display line number {display_line} for route {line} (array format)")
                    elif isinstance(metadata, dict) and 'route_short_name' in metadata:
                        # Old format: direct metadata object
                        display_line = metadata['route_short_name']
                        logger.debug(f"Using display line number {display_line} for route {line} (direct format)")

                # Process times and messages from all destinations
                all_times = []
                minutes_source = None
                minutes_keys = ['minutes', 'scheduled_minutes', 'realtime_minutes']
                
                # Check if we have any realtime data
                has_realtime = False
                has_non_scheduled = False
                for destination, times in line_data.items():
                    if destination == '_metadata':
                        continue
                    for bus in times:
                        if 'realtime_minutes' in bus:
                            has_realtime = True
                        if 'minutes' in bus or 'realtime_minutes' in bus:
                            has_non_scheduled = True

                for destination, times in line_data.items():
                    if destination == '_metadata':  # Skip metadata
                        continue
                    logger.debug(f"Processing destination: {destination}")
                    for bus in times:
                        # Get all available minutes values
                        minutes_values = {}
                        for key in minutes_keys:
                            if key in bus:
                                minutes_values[key] = bus[key]
                        
                        # Prefer realtime over scheduled over basic minutes
                        if 'realtime_minutes' in minutes_values:
                            minutes_source = 'realtime_minutes'
                            minutes = minutes_values['realtime_minutes']
                            minutes_emoji = '⚡'
                        elif 'scheduled_minutes' in minutes_values:
                            minutes_source = 'scheduled_minutes'
                            minutes = minutes_values['scheduled_minutes']
                            # Only show clock if we have a mix of scheduled and realtime/regular times
                            minutes_emoji = '🕒' if has_non_scheduled else ''
                        elif 'minutes' in minutes_values:
                            minutes_source = 'minutes'
                            minutes = minutes_values['minutes']
                            minutes_emoji = ''
                        else:
                            minutes_source = None
                            minutes = None
                            minutes_emoji = ''

                        # Filter out invalid times (negative times less than -5 minutes)
                        try:
                            if minutes is not None and isinstance(minutes, str):
                                # Only clean and check if it might be a negative number
                                if '-' in minutes:
                                    # Remove any quotes and non-numeric characters except minus sign
                                    cleaned_minutes = ''.join(c for c in minutes if c.isdigit() or c == '-')
                                    if cleaned_minutes:
                                        minutes_int = int(cleaned_minutes)
                                        if minutes_int < -5:  # Skip if less than -5 minutes
                                            logger.warning(f"Skipping invalid negative time: {minutes} minutes")
                                            minutes = None
                                            minutes_emoji = ''
                                elif minutes == '0' or minutes == "0'":  # Handle 0 minutes case
                                    minutes = '0'  # Keep the zero
                        except ValueError as e:
                            logger.warning(f"Could not parse minutes value '{minutes}': {e}")
                            minutes = None
                            minutes_emoji = ''

                        time = f"{minutes_emoji}{minutes}" if minutes is not None else ""
                        message = None
                        
                        # Check for special messages
                        if 'message' in bus and bus['message']:  # Only process if message exists and is non-empty
                            if isinstance(bus['message'], dict):
                                msg = bus['message'].get('en', '')
                            else:
                                msg = bus['message']
                                
                            if "Last departure" in msg:
                                message = "Last"
                            elif "Theoretical time" in msg:
                                message = "theor."
                            elif "End of service" in msg:
                                time = ""
                                message = "End of service"
                            else:
                                message = msg
                        logger.debug(f"Time: {time}, Message: {message}, Minutes: {bus.get(minutes_source, None)}, Destination: {destination}")
                        if time or message:  # Only add if we have either a time or a message
                            all_times.append({
                                'time': time,
                                'message': message,
                                'minutes': bus.get(minutes_source, None),
                                'destination': destination
                            })

                # Sort times by minutes:
                # - Extracts only digits from time strings (e.g., "⚡5" -> 5, "🕒10" -> 10)
                # - Valid times (with digits) are sorted normally
                # - Invalid times (None, "--", no digits) are pushed to end using infinity
                all_times.sort(key=lambda x: int(''.join(filter(str.isdigit, str(x['minutes'])))) if x['minutes'] is not None and str(x['minutes']).strip() and any(c.isdigit() for c in str(x['minutes'])) else float('inf'))
                logger.debug(f"All sorted times for line {line}: {all_times}")

                # Only add the bus line if we have actual times or messages to display
                if all_times:
                    waiting_times = []
                    messages = []
                    # Special handling for end of service
                    if any(t['message'] == "End of service" for t in all_times):
                        waiting_times = [""]
                        messages = ["End of service"]
                    # Special handling for last departure
                    elif any(t['message'] == "Last" for t in all_times):
                        last_bus = next(t for t in all_times if t['message'] == "Last")
                        waiting_times = [last_bus['time']]
                        messages = [last_bus['message']]
                    else:
                        # Take all times
                        for time_data in all_times:
                            waiting_times.append(time_data['time'])
                            messages.append(time_data['message'])

                    # Get colors for dithering
                    colors = self.get_line_color(line)

                    bus_times.append({
                        "line": display_line,  # Use display line number
                        "times": waiting_times,
                        "messages": messages,
                        "colors": colors
                    })

            # Update backoff state on success
            if provider_type == 'realtime':
                self._rt_backoff.update_backoff_state(True)
            else:
                self._fallback_backoff.update_backoff_state(True)
            return bus_times, None, stop_name

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if provider_type == 'realtime':
                self._rt_backoff.update_backoff_state(False, error_type='connection' if isinstance(e, requests.exceptions.ConnectionError) else 'timeout')
            else:
                self._fallback_backoff.update_backoff_state(False, error_type='connection' if isinstance(e, requests.exceptions.ConnectionError) else 'timeout')
            return self._get_error_data(), "Connection failed" if isinstance(e, requests.exceptions.ConnectionError) else "Service not responding", ""
        except Exception as e:
            if provider_type == 'realtime':
                self._rt_backoff.update_backoff_state(False, error_type='error')
            else:
                self._fallback_backoff.update_backoff_state(False, error_type='error')
            # If using realtime provider and failed, try fallback
            if self.current_provider == self.provider:
                fallback = self._get_fallback_provider()
                if fallback:
                    logger.info(f"Error with realtime provider, switching to fallback: {fallback}")
                    self.current_provider = fallback
                    self._update_api_urls()
                    self._fallback_backoff.reset()  # Reset backoff for fallback provider
                    return self.get_waiting_times()  # Retry with fallback
            logger.error(f"Error fetching bus times: {e}", exc_info=True)
            return self._get_error_data(), "Service error", ""

    def _get_error_data(self) -> List[Dict]:
        """Return error data structure when something goes wrong"""
        return [
            {"line": "98", "times": [""], "colors": [('black', 0.7), ('white', 0.3)]},
            {"line": "99", "times": [""], "colors": [('black', 0.7), ('white', 0.3)]}
        ]

    def draw_display(self, epd, bus_data=None, weather_data: WeatherData = None, set_base_image=False):
        """Draw the display with bus times and weather info."""
        try:
            # Handle different color definitions
            BLACK = 0 if epd.is_bw_display else epd.BLACK
            WHITE = 1 if epd.is_bw_display else epd.WHITE
            RED = getattr(epd, 'RED', BLACK)  # Fall back to BLACK if RED not available
            YELLOW = getattr(epd, 'YELLOW', BLACK)  # Fall back to BLACK if YELLOW not available

            # Create a new image with white background
            if epd.is_bw_display:
                Himage = Image.new('1', (epd.height, epd.width), WHITE)
            else:
                Himage = Image.new('RGB', (epd.height, epd.width), WHITE)

            draw = ImageDraw.Draw(Himage)
            font_paths = get_font_paths()

            try:
                font_large = ImageFont.truetype(font_paths['dejavu_bold'], 28)
                font_medium = ImageFont.truetype(font_paths['dejavu'], 16)
                font_small = ImageFont.truetype(font_paths['dejavu'], 14)
                font_tiny = ImageFont.truetype(font_paths['dejavu'], 10)
            except Exception as e:
                logger.error(f"Error loading fonts: {e}")
                font_large = font_medium = font_small = font_tiny = ImageFont.load_default()

            MARGIN = 5

            # Draw weather info if available
            if weather_data:
                draw_weather_info(draw, Himage, weather_data, font_paths, epd, MARGIN)

            # Draw bus times if available
            if bus_data:
                y_pos = MARGIN
                for bus in bus_data:
                    route = bus.get('route', '')
                    destination = bus.get('destination', '')
                    due_in = bus.get('due_in', '')
                    
                    # Format text
                    text = f"{route} {destination} {due_in}"
                    draw.text((MARGIN, y_pos), text, font=font_medium, fill=BLACK)
                    y_pos += font_medium.getbbox(text)[3] + 5

            # Rotate the image
            Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)

            return Himage

        except Exception as e:
            logger.error(f"Error drawing display: {e}")
            traceback.print_exc()
            return None

    @lru_cache(maxsize=1024)
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _is_valid_hex_color(self, hex_color: str) -> bool:
        """Validate if a string is a valid hex color code"""
        if not hex_color:
            return False
        # Remove '#' if present
        hex_color = hex_color.lstrip('#')
        # Check if it's a valid hex color (6 characters, valid hex digits)
        return len(hex_color) == 6 and all(c in '0123456789ABCDEFabcdef' for c in hex_color)

    @lru_cache(maxsize=1024)
    def _get_color_distance(self, color1: Tuple[int, int, int], color2: Tuple[int, int, int]) -> float:
        """Calculate Euclidean distance between two RGB colors"""
        return sum((a - b) ** 2 for a, b in zip(color1, color2)) ** 0.5

    @lru_cache(maxsize=1024)
    def _get_dithering_colors(self, target_rgb: Tuple[int, int, int]) -> Tuple[str, str, float]:
        """
        Find the two closest display colors and the mix ratio for dithering.
        Returns (primary_color, secondary_color, primary_ratio)
        """
        # Find the two closest colors
        distances = [(name, self._get_color_distance(target_rgb, rgb))
                    for name, rgb in DISPLAY_COLORS.items()]
        distances.sort(key=lambda x: x[1])
        
        color1, dist1 = distances[0]
        color2, dist2 = distances[1]
        
        # Calculate the ratio (how much of color1 to use)
        total_dist = dist1 + dist2
        if total_dist == 0:
            ratio = 1.0
        else:
            ratio = 1 - (dist1 / total_dist)
            
        # Ensure ratio is between 0.0 and 1.0
        ratio = max(0.0, min(1.0, ratio))
        
        # If the primary color is very dominant (>80%), use it exclusively
        DOMINANCE_THRESHOLD = 0.8
        if ratio >= DOMINANCE_THRESHOLD:
            return color1, color2, 1.0
        
        return color1, color2, ratio

    def set_epd(self, epd):
        """Set the EPD display object for color optimization"""
        self.epd = epd

    @lru_cache(maxsize=1024)
    def get_line_color(self, line: str) -> list:
        """
        Get the optimal colors and ratios for a specific bus line
        Returns a list of (color, ratio) tuples
        Cached to avoid repeated API calls for the same line number
        """
        try:
            if not self.epd:
                logger.warning("EPD not set, falling back to black and white")
                return [('black', 0.7), ('white', 0.3)]

            response = requests.get(f"{self.colors_url}/{line}")
            response.raise_for_status()
            line_colors = response.json()

            # Extract the hex color from the response
            if isinstance(line_colors, dict) and 'background' in line_colors:
                hex_color = line_colors['background']
            else:
                hex_color = line_colors.get(line)

            # Validate hex color
            if not hex_color or not self._is_valid_hex_color(hex_color):
                logger.warning(f"Invalid hex color received for line {line}: {hex_color}")
                return [('black', 0.7), ('white', 0.3)]  # Fallback to black and white

            # Convert hex to RGB
            target_rgb = self._hex_to_rgb(hex_color)
            return find_optimal_colors(target_rgb, self.epd)

        except Exception as e:
            logger.error(f"Error getting line color for {line}: {e}")
            return [('black', 0.7), ('white', 0.3)]  # Fallback to black and white

    def get_api_health(self) -> bool:
        """Check if the API is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health")
            logger.info(f"Health check response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def stop(self):
        """Stop the bus service"""
        self._stop_event.set()

def draw_weather_info(draw, Himage, weather_data: WeatherData, font_paths, epd, MARGIN):
    """Draw weather information in the top right corner."""
    try:
        BLACK = 0 if epd.is_bw_display else epd.BLACK
        
        # Load fonts
        font_medium = ImageFont.truetype(font_paths['dejavu'], 16)
        
        # Format temperature text with correct unit
        unit_symbol = "°F" if weather_data.current.unit == TemperatureUnit.FAHRENHEIT else "°K" if weather_data.current.unit == TemperatureUnit.KELVIN else "°C"
        temp_text = f"{weather_data.current.temperature:.1f}{unit_symbol}"
        
        # Get weather icon
        icon_name = weather_data.current.condition.icon
        icon_path = ICONS_DIR / f"{icon_name}.svg"
        if not icon_path.exists():
            logger.warning(f"Icon not found: {icon_path}")
            icon_path = ICONS_DIR / "cloud.svg"  # fallback icon
            
        # Calculate text size
        text_bbox = draw.textbbox((0, 0), temp_text, font=font_medium)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # Load and size icon to match text height
        icon_size = text_height
        icon = load_svg_icon(icon_path, (icon_size, icon_size), epd)
        
        if icon:
            # Calculate total width and positions
            total_width = text_width + icon_size + 5  # 5px spacing between icon and text
            start_x = Himage.width - total_width - MARGIN
            
            # Draw icon and text
            Himage.paste(icon, (start_x, MARGIN))
            draw.text((start_x + icon_size + 5, MARGIN), 
                     temp_text, font=font_medium, fill=BLACK)
            
    except Exception as e:
        logger.error(f"Error drawing weather info: {e}")
        traceback.print_exc()

def select_lines_to_display(bus_data: List[Dict]) -> List[Dict]:
    """
    Select which 2 lines to display based on earliest arrival times.
    In case of ties (same arrival time), sort by line number.
    Lines with no valid times (e.g. "End of service") are considered last.
    
    Priority order:
    1. Negative arrival times (already late, closest to 0 first)
    2. Buses at stop (0 minutes)
    3. Positive arrival times
    4. No valid times
    """
    def get_earliest_time(times: List[str]) -> tuple[float, bool]:
        """
        Extract the earliest numeric time from a list of time strings
        Returns (time, has_zero) where time is the earliest non-zero time
        and has_zero indicates if there's a bus at the stop
        """
        earliest = float('inf')
        has_zero = False
        has_negative = False
        earliest_negative = float('-inf')
        
        for time_str in times:
            # Skip empty times or special messages
            if not time_str or time_str == "↓↓" or time_str == "⚡↓↓":
                has_zero = True
                continue
                
            # Extract numeric value from time string (e.g. "⚡3'" -> 3)
            # Keep the minus sign for negative times
            digits = ''.join(c for c in time_str if c.isdigit() or c == '-')
            if digits:
                try:
                    time = int(digits)
                    if time == 0:
                        has_zero = True
                    elif time < 0:
                        has_negative = True
                        earliest_negative = max(earliest_negative, time)  # Get the closest to 0
                    else:
                        earliest = min(earliest, time)
                except ValueError:
                    continue
        
        # If we have a negative time, return that
        if has_negative:
            return (earliest_negative, False)
        # Otherwise return the earliest positive time
        return (earliest, has_zero)

    # Create list of lines with their earliest times
    lines_with_times = []
    configured_lines = os.getenv("Lines", "")
    lines_of_interest = _parse_lines(configured_lines) if configured_lines else []
    
    for bus in bus_data:
        # If we have configured lines, only process those
        if lines_of_interest and bus['line'] not in lines_of_interest:
            continue
            
        earliest, has_zero = get_earliest_time(bus['times'])
        lines_with_times.append({
            'line': bus['line'],
            'earliest_time': earliest,
            'has_zero': has_zero,
            'original_data': bus
        })
    
    # Sort by:
    # 1. Negative times first (closest to 0)
    # 2. Has zero (True comes before False)
    # 3. Positive times (smaller first)
    # 4. Line number (for consistent tie-breaking)
    def sort_key(x):
        time = x['earliest_time']
        return (
            time >= 0,  # Negative times first
            not x['has_zero'],  # Then zeros
            abs(time) if time != float('inf') else float('inf'),  # Then by absolute time
            x['line']  # Then by line number
        )
    
    lines_with_times.sort(key=sort_key)
    
    # Take first two lines
    selected = lines_with_times[:2]
    
    # Log selection results
    if len(bus_data) > 2:
        selected_lines = [s['line'] for s in selected]
        dropped_lines = [bus['line'] for bus in bus_data if bus['line'] not in selected_lines]
        logger.info(f"Selected lines {selected_lines} from {len(bus_data)} available lines")
        logger.debug(f"Dropped lines: {dropped_lines}")
        if any(s['earliest_time'] == float('inf') and not s['has_zero'] for s in selected):
            logger.warning("Selected a line with no valid times - this might not be optimal")
    
    # Return original bus data for selected lines
    return [line['original_data'] for line in selected]

def update_display(epd, weather_data: WeatherData = None, bus_data=None, error_message=None, stop_name=None, first_run=False, set_base_image=False):
    """Update the display with new weather and waiting time data"""
    MARGIN = 6

    # Handle different color definitions
    BLACK = epd.BLACK if not epd.is_bw_display else 0
    WHITE = epd.WHITE if not epd.is_bw_display else 1
    RED = getattr(epd, 'RED', BLACK)  # Fall back to BLACK if RED not available
    YELLOW = getattr(epd, 'YELLOW', BLACK)  # Fall back to BLACK if YELLOW not available

    logger.info(f"Display dimensions: {epd.height}x{epd.width} (height x width)")

    # Create a new image with white background
    if epd.is_bw_display:
        Himage = Image.new('1', (epd.height, epd.width), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (epd.height, epd.width), WHITE)
    draw = ImageDraw.Draw(Himage)
    font_paths = get_font_paths()
    try:
        font_large = ImageFont.truetype(font_paths['dejavu_bold'], 32)
        font_medium = ImageFont.truetype(font_paths['dejavu'], 24)
        font_small = ImageFont.truetype(font_paths['dejavu'], 16)
        font_tiny = ImageFont.truetype(font_paths['dejavu'], 12)
        # logger.info(f"Found DejaVu fonts: {font_large}, {font_medium}, {font_small}")
    except:
        font_large = ImageFont.load_default()
        font_medium = font_small = font_large
        logger.warning(f"No DejaVu fonts found, using default: {font_large}, {font_medium}, {font_small}. Install DeJaVu fonts with \n sudo apt install fonts-dejavu\n")
    try:
        emoji_font = ImageFont.truetype(font_paths['emoji'], 16)
        emoji_font_medium = ImageFont.truetype(font_paths['emoji'], 20)
    except:
        emoji_font = font_small
        emoji_font_medium = font_medium
        logger.warning(f"No Noto Emoji font found, using {emoji_font.getname()} instead.")
    if not weather_enabled:
        weather_data = None
        logger.warning("Weather is not enabled, weather data will not be displayed. Do not forget to set OPENWEATHER_API_KEY in .env to enable it.")
    if weather_enabled and weather_data:
        # Get weather icon and temperature
        icon_name = weather_data.current.condition.icon
        temperature = weather_data.current.temperature

        icon_path = ICONS_DIR / f"{icon_name}.svg"
        if not icon_path.exists():
            logger.warning(f"Icon not found: {icon_path}")
            icon_path = ICONS_DIR / "cloud.svg"  # fallback icon
            
        temp_text = f"{temperature:.1f}°"
        
        # Calculate text size
        text_bbox = draw.textbbox((0, 0), temp_text, font=font_small)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # Load and size icon to match text height
        icon_size = text_height
        icon = load_svg_icon(icon_path, (icon_size, icon_size), epd)
        
        if icon:
            # Calculate total width and positions
            total_width = text_width + icon_size + 5  # 5px spacing between icon and text
            start_x = Himage.width - total_width - MARGIN
            
            # Draw icon and text
            Himage.paste(icon, (start_x, MARGIN))
            draw.text((start_x + icon_size + 5, MARGIN), 
                     temp_text, font=font_small, fill=BLACK)
            weather_width = total_width + MARGIN
        else:
            # Fallback to just temperature if icon loading fails
            draw.text((Himage.width - text_width - MARGIN, MARGIN), 
                     temp_text, font=font_small, fill=BLACK)
            weather_width = text_width + MARGIN

          

    stop_name_height = 0
    stop_name = os.getenv("Stop_name_override", stop_name)
    if stop_name:
        stop_name_height, lines = _layout_stop_name(
            draw=draw,
            stop_name=stop_name,
            font_small=font_small,
            weather_width=weather_width if weather_enabled else 0,
            Himage=Himage,
            MARGIN=MARGIN
        )
        
        # Draw the lines
        y_pos = MARGIN
        for line in lines:
            draw.text((MARGIN, y_pos), line, font=font_small, fill=BLACK)
            line_bbox = draw.textbbox((0, 0), line, font=font_small)
            y_pos += line_bbox[3] - line_bbox[1] + MARGIN
        
        logger.debug(f"Stop name height: {stop_name_height}")
            
    # Calculate layout
    HEADER_HEIGHT = stop_name_height
    BOX_HEIGHT = 40
    if show_sunshine or show_precipitation and len(bus_data) > 1:
        if len(lines) > 1:
            BOX_HEIGHT = 25
        else:
            BOX_HEIGHT = 30
        
    else:
        BOX_HEIGHT = 40

    # Select which lines to display if we have more than 2
    if bus_data and len(bus_data) > 2:
        bus_data = select_lines_to_display(bus_data)

    # Adjust spacing based on number of bus lines
    if len(bus_data) == 1:
        # Center the single bus line vertically
        first_box_y = HEADER_HEIGHT + ((Himage.height - HEADER_HEIGHT - BOX_HEIGHT - stop_name_height) // 2)
        logger.debug(f"First box y: {first_box_y}. Header height: {HEADER_HEIGHT}, box height: {BOX_HEIGHT}. Himage height: {Himage.height}")
        second_box_y = first_box_y  # Not used but kept for consistency
    else:  # len(bus_data) == 2 or empty
        # Calculate spacing for two lines to be evenly distributed
        total_available_height = Himage.height - HEADER_HEIGHT - (2 * BOX_HEIGHT)
        SPACING = total_available_height // 3  # Divide remaining space into thirds
        if len(lines) > 1:
            SPACING = min(SPACING - 5, MARGIN)
        first_box_y = HEADER_HEIGHT + SPACING
        second_box_y = first_box_y + BOX_HEIGHT + SPACING//2 

        logger.debug(f"Two-line layout: Header height: {HEADER_HEIGHT}, Available height: {total_available_height}")
        logger.debug(f"Spacing: {SPACING}, First box y: {first_box_y}, Second box y: {second_box_y}")

    logger.debug(f"Bus data: {bus_data}")
    # Filter out bus data with no times or messages
    bus_data = [bus for bus in bus_data if bus.get("times") or bus.get("messages")]
    logger.debug(f"Filtered bus data: {bus_data}")

    # Draw bus information
    for idx, bus in enumerate(bus_data):
        y_position = first_box_y if idx == 0 else second_box_y

        # Draw dithered box with line number
        colors_with_ratios = bus['colors']
        
        line_text_bbox = draw.textbbox((0, 0), bus['line'], font=font_large)
      
        line_text_width = line_text_bbox[2] - line_text_bbox[0]

        line_text_width =  max(min(35 + (line_text_width), line_text_width), 50)


        stop_name_bbox = draw_multicolor_dither_with_text(
            draw=draw,
            epd=epd,
            x=10,
            y=y_position,
            width=line_text_width,
            height=BOX_HEIGHT,
            text=bus['line'],
            colors_with_ratios=colors_with_ratios,
            font=font_large
        )


        # Draw arrow
        draw.text((line_text_width + MARGIN+10, y_position + (BOX_HEIGHT - 24) // 2), "→",
                  font=font_medium, fill=BLACK)
        # Calculate width of arrow
        arrow_bbox = draw.textbbox((0, 0), "→", font=font_medium)
        arrow_width = arrow_bbox[2] - arrow_bbox[0] + MARGIN

        # Process times and messages
        times = bus["times"]
        messages = bus.get("messages", [None] * len(times))

        x_pos = line_text_width + arrow_width + MARGIN + MARGIN
        y_pos = y_position + (BOX_HEIGHT - 24) // 2

        # Calculate maximum available width
        max_width = Himage.width - x_pos - MARGIN - MARGIN  # Available width
        times_shown = 0
        len_times = len(times)
        if len_times <=2:
            EXTRA_SPACING = 10
        else:
            EXTRA_SPACING = 0
        for time, message in zip(times, messages):
            if not time.lower().endswith("'"):
                time = str(time) + "'"
            if time.lower()=="0'" or time.lower()=="0":
                time = "↓↓"
            if  time.lower()=="⚡0'" or time.lower()=="⚡ 0":
                time = "⚡↓↓"
            # Calculate width needed for this time + message
            time_bbox = draw.textbbox((0, 0), time, font=font_medium)
            time_width = time_bbox[2] - time_bbox[0]


            message_width = 0
            if message:
                msg_text = message
                msg_text2 = None
                if message == "Last":
                    msg_text = "Last"
                    msg_text2 = "departure"
                elif message == "theor.":
                    msg_text = "(theor.)"
                elif message:
                    msg_text = message
                msg_bbox = draw.textbbox((0, 0), msg_text, font=font_small)
                if msg_text2:
                    msg_bbox2 = draw.textbbox((0, 0), msg_text2, font=font_small)
                    msg_width2 = msg_bbox2[2] - msg_bbox2[0]
                    message_width = max(msg_width2, msg_bbox[2] - msg_bbox[0]) + 5
                else:
                    message_width = msg_bbox[2] - msg_bbox[0] + 5  # 5px spacing

            # Check if we have space for this time + message + spacing
            if times_shown > 0 and (time_width + message_width + MARGIN + EXTRA_SPACING > max_width):
                break

            # Check if there is an emoji to show
            if '🕒' in time or '⚡' in time:
                emoji_text = '🕒' if '🕒' in time else '⚡'
                emoji_bbox = draw.textbbox((0, 0), emoji_text, font=emoji_font)
                emoji_width = emoji_bbox[2] - emoji_bbox[0]
                time_text = time.replace('🕒', '').replace('⚡', '')
                time_bbox = draw.textbbox((0, 0), time_text, font=font_medium)
                time_text_width = time_bbox[2] - time_bbox[0]
                time_width = time_text_width + emoji_width
                draw.text((x_pos + MARGIN - 2, y_pos + 2), emoji_text, font=emoji_font_medium, fill=BLACK)
                draw.text((x_pos + MARGIN + emoji_width, y_pos ), time_text, font=font_medium, fill=BLACK)
            else:
                draw.text((x_pos + MARGIN, y_pos), time, font=font_medium, fill=BLACK)



            # Draw message if present
            if message:
                msg_x = x_pos + time_width + MARGIN + 2
                if message == "Last":
                    draw.text((msg_x, y_pos), msg_text,
                              font=font_tiny, fill=BLACK)
                    if msg_text2:
                        font_bbox = font_tiny.getbbox("Aj")  # Get bounding box of test string
                        font_height = font_bbox[3] - font_bbox[1]  # Calculate height from bounding box
                        draw.text((msg_x, y_pos + font_height), msg_text2,
                              font=font_tiny, fill=BLACK)
                    break  # Don't show more times after "Last departure"
                elif message == "theor.":
                    draw.text((msg_x, y_pos + MARGIN), "(theor.)",
                              font=font_small, fill=BLACK)
                elif message:
                    draw.text((msg_x, y_pos + MARGIN), msg_text,
                              font=font_small, fill=BLACK)

            # Move x position for next time
            x_pos += time_width + message_width + MARGIN + EXTRA_SPACING  # Add spacing between times
            max_width -= (time_width + message_width + MARGIN + EXTRA_SPACING)  # Deduct used width
            times_shown += 1

    # Draw current time at the bottom
    current_time = datetime.now().strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    time_height = time_bbox[3] - time_bbox[1]

    # Calculate available space for weather info
    available_width = Himage.width - time_width - (3 * MARGIN)  # Space left of the time
    
    # If weather data is available, draw sunshine hours and precipitation in the bottom left

    logger.debug(f"Show sunshine hours setting: {show_sunshine}")
    logger.debug(f"Show precipitation setting: {show_precipitation}")
    
    # Adjust time position based on number of bus lines
    if len(bus_data) == 1:
        time_y = Himage.height - time_height - MARGIN
    else:
        time_y = Himage.height - time_height - MARGIN

    footer_weather_font = font_small if len(bus_data) < 2 else font_tiny

    

    # Draw the time in bottom right
    draw.text((Himage.width - time_width - MARGIN, time_y),
              current_time, font=footer_weather_font, fill=BLACK)
    
    if  weather_enabled and weather_data and weather_data.daily_forecast:
        try:
            # Calculate positions
            x_pos = MARGIN
            y_pos = time_y  # Align with current time
            
            # Load weather icons if needed
            sun_icon = None
            umbrella_icon = None
            
            if show_sunshine:
                sunshine_duration = weather_data.daily_forecast[0].sunshine_duration
                sunshine_hours = sunshine_duration.total_seconds() / 3600
                sun_icon = load_svg_icon(ICONS_DIR / "sun.svg", (time_height, time_height), epd)
                logger.debug(f"Sunshine duration for today: {sunshine_duration} ({sunshine_hours:.1f}h)")
            
            if show_precipitation:
                precipitation = weather_data.daily_forecast[0].precipitation_amount
                umbrella_icon = load_svg_icon(ICONS_DIR / "umbrella.svg", (time_height, time_height), epd)
                logger.debug(f"Precipitation for today: {precipitation:.1f}mm")
            
            # Calculate total width needed
            total_width_needed = 0
            if show_sunshine:
                sun_text = f"{sunshine_hours:.1f}h"
                sun_bbox = draw.textbbox((0, 0), sun_text, font=font_small)
                sun_width = sun_bbox[2] - sun_bbox[0] + time_height + 2  # icon + text + spacing
                total_width_needed += sun_width + MARGIN
            
            if show_precipitation:
                rain_text = f"{precipitation:.1f}mm"
                rain_bbox = draw.textbbox((0, 0), rain_text, font=font_small)
                rain_width = rain_bbox[2] - rain_bbox[0] + time_height + 2  # icon + text + spacing
                total_width_needed += rain_width
            
            # Only draw if we have enough space
            if total_width_needed < available_width:
                # Draw sun icon and text if enabled
                if show_sunshine and sun_icon:
                    sun_text = f"{sunshine_hours:.1f}h"
                    sun_bbox = draw.textbbox((0, 0), sun_text, font=footer_weather_font)
                    sun_width = sun_bbox[2] - sun_bbox[0]
                    
                    Himage.paste(sun_icon, (x_pos, y_pos))
                    draw.text((x_pos + time_height + 2, y_pos), sun_text, font=footer_weather_font, fill=BLACK)
                    x_pos += time_height + sun_width + MARGIN + 5  # Add spacing after sun info
                
                # Draw umbrella icon and text if enabled
                if show_precipitation and umbrella_icon:
                    rain_text = f"{precipitation:.1f}mm"
                    Himage.paste(umbrella_icon, (x_pos, y_pos))
                    draw.text((x_pos + time_height + 2, y_pos), rain_text, font=footer_weather_font, fill=BLACK)
            else:
                logger.debug(f"Not enough horizontal space for weather info. Need {total_width_needed}px, have {available_width}px")
            
            logger.debug(f"Drew weather info with icons (sunshine: {show_sunshine}, precipitation: {show_precipitation})")
            
        except Exception as e:
            logger.warning(f"Could not display weather info: {e}")
            logger.debug(traceback.format_exc())


    # Draw error message if present
    if error_message:
        error_bbox = draw.textbbox((0, 0), error_message, font=font_small)
        error_width = error_bbox[2] - error_bbox[0]
        error_x = (Himage.width - error_width) // 2
        error_y = time_y + time_height + MARGIN if len(bus_data) == 1 else second_box_y + BOX_HEIGHT + MARGIN
        draw.text((error_x, error_y), error_message, font=font_small, fill=RED)

    # Draw a border around the display
    border_color = getattr(epd, 'RED', 0)  # Fall back to BLACK if RED not available
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=border_color)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)
    with display_lock:
        # Convert image to buffer
        buffer = epd.getbuffer(Himage)

        # Add debug log before display command
        logger.debug("About to call epd.display() with new buffer")
        if hasattr(epd, 'displayPartial'):
            if set_base_image:
                logger.debug("Setting base image for bus display mode")
                epd.init()
                epd.displayPartBaseImage(buffer)
            else:
                logger.debug("Using partial display update")
                epd.displayPartial(buffer)
        else:
            logger.debug("Using full display update")
            epd.display(buffer)

def _find_text_segments(text: str) -> list:
    """Find natural segments in text based on priority delimiters."""
    # First priority: sections divided by dash, en-dash, em-dash, slash, comma
    priority1_delimiters = [',', '/', '-', '–', '—']  # en-dash (–) and em-dash (—)
    
    # Check if we have any priority 1 delimiters
    for delimiter in priority1_delimiters:
        if delimiter in text:
            return [seg.strip() for seg in text.split(delimiter) if seg.strip()]
    
    # Second priority: blocks divided by spaces
    return [word for word in text.split() if word]

def _calculate_text_layout(draw, text: str, font, first_line_width: int, second_line_width: int, ellipsis_width: int, margin: int) -> tuple[list, int]:
    """
    Calculate optimal text layout for given width constraints.
    Returns: (lines, total_height)
    """
    segments = _find_text_segments(text)
    if not segments:
        return [], 0
        
    # Get line height from a sample text
    line_bbox = draw.textbbox((0, 0), "Aj", font=font)
    line_height = line_bbox[3] - line_bbox[1]
    
    # Try to fit segments on lines
    lines = []
    current_line = []
    current_width = 0
    
    for segment in segments:
        # Calculate segment width including a space
        segment_bbox = draw.textbbox((0, 0), segment + " ", font=font)
        segment_width = segment_bbox[2] - segment_bbox[0]
        
        # If this is first segment on the line
        if not current_line:
            current_line.append(segment)
            current_width = segment_width
            continue
            
        # Check if segment fits on current line
        # Use first line width for first line, second line width for subsequent lines
        max_width = first_line_width if not lines else second_line_width
        if current_width + segment_width <= max_width:
            current_line.append(segment)
            current_width += segment_width
        else:
            # Start new line
            lines.append(" ".join(current_line))
            current_line = [segment]
            current_width = segment_width
    
    # Add last line
    if current_line:
        lines.append(" ".join(current_line))
    
    # Handle line truncation with ellipsis
    if len(lines) > 2:
        # Keep first line as is if it fits
        first_line_bbox = draw.textbbox((0, 0), lines[0], font=font)
        if first_line_bbox[2] > first_line_width:
            # First line needs truncation
            words = lines[0].split()
            truncated = []
            current_width = 0
            for word in words:
                word_bbox = draw.textbbox((0, 0), ((" " if truncated else "") + word), font=font)
                word_width = word_bbox[2] - word_bbox[0]
                if current_width + word_width + ellipsis_width <= first_line_width:
                    truncated.append(word)
                    current_width += word_width
                else:
                    break
            lines[0] = " ".join(truncated) + "..."
        
        # Combine remaining text and truncate for second line
        remaining_text = " ".join([line for line in lines[1:]])
        words = remaining_text.split()
        truncated = []
        current_width = 0
        for word in words:
            word_bbox = draw.textbbox((0, 0), ((" " if truncated else "") + word), font=font)
            word_width = word_bbox[2] - word_bbox[0]
            if current_width + word_width + ellipsis_width <= second_line_width:
                truncated.append(word)
                current_width += word_width
            else:
                break
        if truncated:
            lines = [lines[0], " ".join(truncated) + "..."]
        else:
            lines = [lines[0]]
    elif len(lines) == 2:
        # Check if second line needs truncation
        second_line_bbox = draw.textbbox((0, 0), lines[1], font=font)
        if second_line_bbox[2] > second_line_width:
            words = lines[1].split()
            truncated = []
            current_width = 0
            for word in words:
                word_bbox = draw.textbbox((0, 0), ((" " if truncated else "") + word), font=font)
                word_width = word_bbox[2] - word_bbox[0]
                if current_width + word_width + ellipsis_width <= second_line_width:
                    truncated.append(word)
                    current_width += word_width
                else:
                    break
            if truncated:
                lines[1] = " ".join(truncated) + "..."
            else:
                lines.pop()
    
    total_height = len(lines) * (line_height + margin)
    return lines, total_height

def _layout_stop_name(draw, stop_name: str, font_small, weather_width: int, Himage, MARGIN: int) -> tuple[int, list]:
    """
    Layout stop name text optimally.
    Returns: (total_height, lines)
    """
    if not stop_name:
        return 0, []
        
    # Calculate available widths for each line
    first_line_width = Himage.width - weather_width - 2*MARGIN
    second_line_width = Himage.width - 2*MARGIN
    
    # Get width of ellipsis
    ellipsis_bbox = draw.textbbox((0, 0), "...", font=font_small)
    ellipsis_width = ellipsis_bbox[2] - ellipsis_bbox[0]
    
    # Try to fit everything on one line first
    full_text_bbox = draw.textbbox((0, 0), stop_name, font=font_small)
    full_text_width = full_text_bbox[2] - full_text_bbox[0]
    
    if full_text_width <= first_line_width:
        # Everything fits on one line
        return full_text_bbox[3] - full_text_bbox[1] + MARGIN, [stop_name]
    
    # Need to split into multiple lines
    lines, total_height = _calculate_text_layout(
        draw=draw,
        text=stop_name,
        font=font_small,
        first_line_width=first_line_width,
        second_line_width=second_line_width,
        ellipsis_width=ellipsis_width,
        margin=MARGIN
    )
    
    return total_height, lines