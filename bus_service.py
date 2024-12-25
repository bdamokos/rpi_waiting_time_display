from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import requests
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

from weather import WEATHER_ICONS
logger = logging.getLogger(__name__)

dotenv.load_dotenv(override=True)

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

Stop = _get_stop_config()
Lines = os.getenv("Lines")
bus_api_base_url = os.getenv("BUS_API_BASE_URL", "http://localhost:5001/")
bus_provider = os.getenv("Provider", "stib")
logging.debug(f"Bus provider: {bus_provider}. Base URL: {bus_api_base_url}. Monitoring lines: {Lines} and stop: {Stop}")

DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))
weather_enabled = True if os.getenv("OPENWEATHER_API_KEY") else False
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
    """
    if not lines_str:
        logger.error("No bus lines configured")
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
        self.provider = os.getenv("Provider", "stib")
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
    
    @lru_cache(maxsize=1024)
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

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
        
        return color1, color2, ratio

    @lru_cache(maxsize=1024)
    def get_line_color(self, line: str) -> list:
        """
        Get the optimal colors and ratios for a specific bus line
        Returns a list of (color, ratio) tuples
        Cached to avoid repeated API calls for the same line number
        """
        try:
            response = requests.get(f"{self.colors_url}/{line}")
            response.raise_for_status()
            line_colors = response.json()

            # Extract the hex color from the response
            if isinstance(line_colors, dict) and 'background' in line_colors:
                hex_color = line_colors['background']
            else:
                hex_color = line_colors.get(line)

            # Convert hex to RGB
            target_rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
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

            bus_times = []
            for line in self.lines_of_interest:
                logger.debug(f"Processing line {line}")
                line_data = stop_data.get("lines", {}).get(line, {})
                logger.debug(f"Line data found: {line_data}")
                
                if not line_data:
                    logger.warning(f"No data found for line {line}")
                    bus_times.append({
                        "line": line,
                        "times": [],
                        "colors": [('black', 0.7), ('white', 0.3)],
                        "message": None
                    })
                    continue

                # Process times and messages from all destinations
                all_times = []
                minutes_source = None
                minutes_keys = ['minutes', 'scheduled_minutes', 'realtime_minutes']
                
                # Get line display name from metadata if available
                display_line = line  # Default to route ID
                if '_metadata' in line_data and 'route_short_name' in line_data['_metadata']:
                    display_line = line_data['_metadata']['route_short_name']
                    logger.debug(f"Using display line number {display_line} for route {line}")
                
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
                            minutes_emoji = '🕒'
                        elif 'minutes' in minutes_values:
                            minutes_source = 'minutes'
                            minutes = minutes_values['minutes']
                            minutes_emoji = ''
                        else:
                            minutes_source = None
                            minutes = None
                            minutes_emoji = ''
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
                                time = ""
                                message = "End of service"
                            else:
                                message = msg
                        logger.debug(f"Time: {time}, Message: {message}, Minutes: {bus.get(minutes_source, None)}, Destination: {destination}")
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

                # Take all available times
                waiting_times = []
                messages = []
                if all_times:
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

                # Ensure at least one slot
                if not waiting_times:
                    waiting_times = [""]
                    messages = [None]

                # Get colors for dithering
                colors = self.get_line_color(line)

                bus_times.append({
                    "line": display_line,  # Use display line number
                    "times": waiting_times,
                    "messages": messages,
                    "colors": colors
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
            {"line": "56", "times": [""], "colors": [('black', 0.7), ('white', 0.3)]},
            {"line": "59", "times": [""], "colors": [('black', 0.7), ('white', 0.3)]}
        ]

if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.DEBUG)
    bus_service = BusService()
    print(bus_service.get_waiting_times()) 


def update_display(epd, weather_data=None, bus_data=None, error_message=None, stop_name=None, first_run=False):
    """Update the display with new weather and waiting timesdata"""
    MARGIN = 8

    # Handle different color definitions
    BLACK = epd.BLACK
    WHITE = epd.WHITE
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
    if weather_enabled:
        weather_icon = WEATHER_ICONS.get(weather_data['description'], '')
        logger.debug(f"Weather icon: {weather_icon}, description: {weather_data['description']}, font: {emoji_font.getname()}")
        temp_text = f"{weather_data['temperature']}°"

        weather_text = f"{temp_text}"
        weather_icon_bbox = draw.textbbox((0, 0), weather_icon, font=emoji_font)
        weather_icon_width = weather_icon_bbox[2] - weather_icon_bbox[0]
        weather_bbox = draw.textbbox((0, 0), weather_text, font=font_small)
        weather_text_width = weather_bbox[2] - weather_bbox[0]
        weather_width = weather_text_width + weather_icon_width
        draw.text((Himage.width - weather_width - weather_icon_width - MARGIN, MARGIN), weather_icon, font=emoji_font, fill=BLACK)
        draw.text((Himage.width - weather_width - MARGIN, MARGIN), weather_text, font=font_small, fill=BLACK)
    stop_name_height = 0
    if stop_name:
        stop_name_bbox = draw.textbbox((0, 0), stop_name, font=font_small)
        stop_name_width = stop_name_bbox[2] - stop_name_bbox[0]
        if (weather_enabled and (Himage.width - weather_width - stop_name_width - MARGIN) < 0) or (not weather_enabled and (Himage.width - stop_name_width - MARGIN) < 0):
            logger.debug(f"Stop name width: {stop_name_width}, weather width: {weather_width if weather_enabled else 0}, total width: {Himage.width}, margin: {MARGIN}. The total width is too small for the stop name and weather.")
            # Split stop name into two lines
            stop_name_parts = stop_name.split(' ', 1)
            logger.debug(f"Stop name parts: {stop_name_parts}")
            if len(stop_name_parts) > 1:
                line1, line2 = stop_name_parts
            else:
                line1 = stop_name
                line2 = ""

            # Draw first line
            draw.text((MARGIN, MARGIN), line1, font=font_small, fill=BLACK)
            line1_bbox = draw.textbbox((0, 0), line1, font=font_small)
            stop_name_height = line1_bbox[3] - line1_bbox[1] + MARGIN


            # Draw second line if it exists
            if line2:
                line1_bbox = draw.textbbox((0, 0), line1, font=font_small)
                line1_height = line1_bbox[3] - line1_bbox[1]
                draw.text((MARGIN, MARGIN + line1_height+MARGIN), line2, font=font_small, fill=BLACK)
                line2_bbox = draw.textbbox((0, 0), line2, font=font_small)
                line2_height = line2_bbox[3] - line2_bbox[1]
                stop_name_height = line1_height + line2_height + MARGIN + MARGIN + MARGIN
                logger.debug(f"Stop name height: {stop_name_height}")
        else:
            logger.debug(f"Stop name width: {stop_name_width}, weather width: {weather_width if weather_enabled else 0}, total width: {Himage.width}, margin: {MARGIN}")
            draw.text((MARGIN, MARGIN), stop_name, font=font_small, fill=BLACK)
            stop_name_bbox = draw.textbbox((0, 0), stop_name, font=font_small)
            stop_name_height = stop_name_bbox[3] - stop_name_bbox[1] + MARGIN
    logger.debug(f"Stop name height: {stop_name_height}")
    # Calculate layout

    HEADER_HEIGHT = stop_name_height + MARGIN
    BOX_HEIGHT = 40

    # Adjust spacing based on number of bus lines
    if len(bus_data) == 1:
        # Center the single bus line vertically
        first_box_y = MARGIN + HEADER_HEIGHT + ((Himage.height - HEADER_HEIGHT - BOX_HEIGHT - stop_name_height) // 2)
        logger.debug(f"First box y: {first_box_y}. Header height: {HEADER_HEIGHT}, box height: {BOX_HEIGHT}. Himage height: {Himage.height}")
        second_box_y = first_box_y  # Not used but kept for consistency
    elif len(bus_data) == 2:
        # Calculate spacing for two lines to be evenly distributed
        total_available_height = Himage.height - HEADER_HEIGHT - (2 * BOX_HEIGHT)
        SPACING = total_available_height // 3  # Divide remaining space into thirds

        first_box_y = HEADER_HEIGHT + SPACING
        second_box_y = first_box_y + BOX_HEIGHT + SPACING

        logger.debug(f"Two-line layout: Header height: {HEADER_HEIGHT}, Available height: {total_available_height}")
        logger.debug(f"Spacing: {SPACING}, First box y: {first_box_y}, Second box y: {second_box_y}")
    else:
        logger.error(f"Unexpected number of bus lines: {len(bus_data)}. Display currently supports up to 2 lines from the same provider and stop.")
        draw.text((MARGIN, MARGIN), "Error, see logs", font=font_large, fill=RED)
        return




    logger.debug(f"Bus data: {bus_data}")
    # Filter out bus data with no times or messages
    bus_data = [bus for bus in bus_data if bus.get("times") or bus.get("messages")]
    logger.debug(f"Filtered bus data: {bus_data}")

    # Draw bus information
    for idx, bus in enumerate(bus_data):
        y_position = first_box_y if idx == 0 else second_box_y

        # Draw dithered box with line number
        colors_with_ratios = bus['colors']
        line_text_length = len(bus['line'])
        line_text_width = 35 + (line_text_length * 9)
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

    # Adjust time position based on number of bus lines
    if len(bus_data) == 1:
        time_y = Himage.height - time_height - MARGIN
    else:
        time_y = Himage.height - time_height - MARGIN

    draw.text((Himage.width - time_width - MARGIN, time_y),
              current_time, font=font_small, fill=BLACK)

    # Draw error message if present
    if error_message:
        error_bbox = draw.textbbox((0, 0), error_message, font=font_small)
        error_width = error_bbox[2] - error_bbox[0]
        error_x = (Himage.width - error_width) // 2
        error_y = time_y + time_height + MARGIN if len(bus_data) == 1 else second_box_y + BOX_HEIGHT + MARGIN
        draw.text((error_x, error_y), error_message, font=font_small, fill=RED)

    # Draw a border around the display
    border_color = getattr(epd, 'RED', epd.BLACK)  # Fall back to BLACK if RED not available
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=border_color)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)
    with display_lock:
        # Convert image to buffer
        buffer = epd.getbuffer(Himage)

        # Add debug log before display command
        logger.debug("About to call epd.display() with new buffer")
        epd.display(buffer)