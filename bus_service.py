import requests
import logging
from typing import List, Dict, Tuple
import os
import dotenv
from colorsys import rgb_to_hsv

logger = logging.getLogger(__name__)
dotenv.load_dotenv()
Stop = os.getenv("Stops")
Lines = os.getenv("Lines")
bus_api_base_url = os.getenv("BUS_API_BASE_URL")

# Define our available colors and their RGB values
DISPLAY_COLORS = {
    'black': (0, 0, 0),
    'white': (255, 255, 255),
    'red': (255, 0, 0),
    'yellow': (255, 255, 0)
}

class BusService:
    def __init__(self):
        self.base_url = bus_api_base_url
        self.api_url = f"{self.base_url}/api/stib/waiting_times"
        self.colors_url = f"{self.base_url}/api/stib/colors"
        self.stop_id = Stop
        self.lines_of_interest = [line.strip() for line in Lines.split(",")]
        
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
            return self._get_error_data(), "API not available", ""

        try:
            response = requests.get(self.api_url)
            response.raise_for_status()
            data = response.json()

            # Extract waiting times for our stop
            stop_data = data["stops_data"].get(self.stop_id, {})
            if not stop_data:
                logger.error(f"Stop {self.stop_id} not found in response")
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
                        "colors": ('black', 'black', 1.0)
                    })
                    continue

                # Get the first destination's times
                first_destination = next(iter(line_data.values()))
                logger.debug(f"First destination data: {first_destination}")
                waiting_times = [f"{bus['minutes']}'" for bus in first_destination[:2]]
                logger.debug(f"Extracted waiting times: {waiting_times}")
                
                # Pad with "--" if we have less than 2 times
                while len(waiting_times) < 2:
                    waiting_times.append("--")

                # Get colors for dithering
                primary_color, secondary_color, ratio = self.get_line_color(line)

                bus_times.append({
                    "line": line,
                    "times": waiting_times,
                    "colors": (primary_color, secondary_color, ratio)
                })

            return bus_times, None, stop_name

        except requests.exceptions.ConnectionError:
            return self._get_error_data(), "Connection failed", ""
        except Exception as e:
            logger.error(f"Error fetching bus times: {e}")
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