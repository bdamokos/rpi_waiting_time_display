import requests
import logging
from typing import List, Dict, Tuple
import os
import dotenv
import log_config
import socket

logger = logging.getLogger(__name__)

dotenv.load_dotenv(override=True)
Stop = os.getenv("Stops")
Lines = os.getenv("Lines")
bus_api_base_url = os.getenv("BUS_API_BASE_URL", "http://localhost:5001/")
bus_provider = os.getenv("Provider", "stib")
logging.debug(f"Bus provider: {bus_provider}. Base URL: {bus_api_base_url}. Monitoring lines: {Lines} and stop: {Stop}")

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
    """
    if not lines_str:
        logger.error("No bus lines configured")
        return []
    
    # Remove any whitespace
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
            return [str(int(item)) for item in items]
        except ValueError as e:
            logger.error(f"Invalid number in list format: {e}")
            return []
    
    try:
        # Try to parse as a single number
        return [str(int(lines_str))]
    except ValueError:
        # If that fails, try to split and parse as list
        # Remove all whitespace and split on comma
        cleaned = ''.join(lines_str.split())  # Remove all whitespace
        cleaned = cleaned.replace(',', ' ').split()  # Split on comma or space
        
        # Convert to integers and back to strings to validate and normalize
        try:
            return [str(int(line)) for line in cleaned]
        except ValueError as e:
            logger.error(f"Invalid bus line number format: {e}")
            return []

class BusService:
    def __init__(self):
        self.base_url = self._resolve_base_url()
        self.provider = bus_provider
        logger.debug(f"Bus provider: {self.provider}. Resolved Base URL: {self.base_url}")
        self.api_url = f"{self.base_url}/api/{self.provider}/waiting_times"
        logger.debug(f"API URL: {self.api_url}")
        self.colors_url = f"{self.base_url}/api/{self.provider}/colors"
        logger.debug(f"Colors URL: {self.colors_url}")
        self.stop_id = Stop
        logger.debug(f"Stop ID: {self.stop_id}")
        self.lines_of_interest = _parse_lines(Lines)
        logger.info(f"Monitoring bus lines: {self.lines_of_interest}")
        
    def _resolve_base_url(self) -> str:
        """Resolve the base URL, handling .local domains"""
        base_url = bus_api_base_url.lower()
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
                return "http://127.0.0.1:5001/"
        return base_url

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _get_color_distance(self, color1: Tuple[int, int, int], color2: Tuple[int, int, int]) -> float:
        """Calculate Euclidean distance between two RGB colors"""
        return sum((a - b) ** 2 for a, b in zip(color1, color2)) ** 0.5

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
        
        return color1, color2, ratio

    def get_line_color(self, line: str) -> Tuple[str, str, float]:
        """
        Get the dithering colors and ratio for a specific bus line
        Returns (primary_color, secondary_color, primary_ratio)
        """
        try:
            response = requests.get(f"{self.colors_url}/{line}")
            response.raise_for_status()
            line_colors = response.json()

            # Check if response has multiple keys and get background color if available
            if isinstance(line_colors, dict) and 'background' in line_colors:
                line_colors = line_colors['background']
            
                hex_color = line_colors
            else:
                hex_color = line_colors.get(line)
            if not hex_color:
                logger.error(f"Color not found for line {line}")
                return 'black', 'black', 1.0
                
            target_rgb = self._hex_to_rgb(hex_color)
            return self._get_dithering_colors(target_rgb)
            
        except Exception as e:
            logger.error(f"Error fetching line color: {e}")
            return 'black', 'black', 1.0

    def get_api_health(self) -> bool:
        """Check if the API is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health")
            logger.info(f"Health check response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_waiting_times(self) -> tuple[List[Dict], str, str]:
        """Fetch and process waiting times for our bus lines"""
        # First check API health
        if not self.get_api_health():
            logger.error("API not available")
            return self._get_error_data(), "API not available", ""

        try:
            response = requests.get(self.api_url, timeout=30)  # 30 second timeout
            logger.debug(f"API response time: {response.elapsed.total_seconds():.3f} seconds")
            response.raise_for_status()
            data = response.json()
            logger.debug(f"API response: {data}")

            stops_data_location_keys = ['stops_data', 'stops']
            for key in stops_data_location_keys:
                if key in data:
                    stop_data = data[key].get(self.stop_id, {})
                    logger.debug(f"Stop data found: {stop_data}")
                    break

            # Extract waiting times for our stop
            if not stop_data:
                logger.error(f"Stop '{self.stop_id}' not found in response, as no stop data was found")
                return self._get_error_data(), "Stop data not found", ""

            # Get stop name
            stop_name = stop_data.get("name", "")
            logger.debug(f"Stop name: {stop_name}")

            bus_times = []
            for line in self.lines_of_interest:
                logger.debug(f"Processing line {line}")
                line_data = stop_data.get("lines", {}).get(line, {})
                logger.debug(f"Line data found: {line_data}")
                
                if not line_data:
                    logger.warning(f"No data found for line {line}")
                    bus_times.append({
                        "line": line,
                        "times": ["--", "--"],
                        "colors": ('black', 'black', 1.0),
                        "message": None
                    })
                    continue

                # Process times and messages from all destinations
                all_times = []
                minutes_source = None
                minutes_keys = ['minutes', 'scheduled_minutes', 'realtime_minutes']
                for destination, times in line_data.items():
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
                            minutes_emoji = '🕒'
                        elif 'minutes' in minutes_values:
                            minutes_source = 'minutes'
                            minutes = minutes_values['minutes']
                            minutes_emoji = ''
                        else:
                            minutes_source = None
                            minutes = None
                        time = f"{minutes_emoji}{minutes}"
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
                                time = "--"
                                message = "End of service"
                        logger.debug(f"Time: {time}, Message: {message}, Minutes: {bus.get(minutes_source, None)}, Destination: {destination}")
                        all_times.append({
                            'time': time,
                            'message': message,
                            'minutes': bus.get(minutes_source, None),
                            'destination': destination
                        })

                # Sort times by minutes
                all_times.sort(key=lambda x: x['minutes'])
                logger.debug(f"All sorted times for line {line}: {all_times}")

                # Take all available times
                waiting_times = []
                messages = []
                if all_times:
                    # Special handling for end of service
                    if any(t['message'] == "End of service" for t in all_times):
                        waiting_times = ["--"]
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

                # Ensure at least one slot
                if not waiting_times:
                    waiting_times = ["--"]
                    messages = [None]

                # Get colors for dithering
                primary_color, secondary_color, ratio = self.get_line_color(line)

                bus_times.append({
                    "line": line,
                    "times": waiting_times,
                    "messages": messages,
                    "colors": (primary_color, secondary_color, ratio)
                })

            return bus_times, None, stop_name

        except requests.exceptions.ConnectionError:
            return self._get_error_data(), "Connection failed", ""
        except Exception as e:
            logger.error(f"Error fetching bus times: {e}", exc_info=True)
            return self._get_error_data(), f"Error: {str(e)}", ""

    def _get_error_data(self) -> List[Dict]:
        """Return error data structure when something goes wrong"""
        return [
            {"line": "56", "times": ["--", "--"], "colors": ('black', 'black', 1.0)},
            {"line": "59", "times": ["--", "--"], "colors": ('black', 'black', 1.0)}
        ]

if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.DEBUG)
    bus_service = BusService()
    print(bus_service.get_waiting_times()) 