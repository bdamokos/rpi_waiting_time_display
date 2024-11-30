import requests
import logging
from typing import List, Dict
import os
import dotenv

logger = logging.getLogger(__name__)
dotenv.load_dotenv()
Stop = os.getenv("Stops")
Lines = os.getenv("Lines")
bus_api_base_url = os.getenv("BUS_API_BASE_URL")

class BusService:
    def __init__(self):
        self.base_url = bus_api_base_url
        self.api_url = f"{self.base_url}/api/stib/waiting_times"
        self.stop_id = Stop
        self.lines_of_interest = Lines.split(",")

    def get_api_health(self) -> bool:
        """Check if the API is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health")
            logger.info(f"Health check response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_waiting_times(self) -> tuple[List[Dict], str]:
        """Fetch and process waiting times for our bus lines"""
        # First check API health
        if not self.get_api_health():
            return self._get_error_data(), "API not available"

        try:
            response = requests.get(self.api_url)
            response.raise_for_status()
            data = response.json()

            # Extract waiting times for our stop
            stop_data = data["stops_data"].get(self.stop_id, {})
            if not stop_data:
                logger.error(f"Stop {self.stop_id} not found in response")
                return self._get_error_data(), "Stop data not found"

            bus_times = []
            for line in self.lines_of_interest:
                line_data = stop_data.get("lines", {}).get(line, {})
                if not line_data:
                    bus_times.append({"line": line, "times": ["--", "--"]})
                    continue

                # Get the first destination's times (we only need one direction)
                first_destination = next(iter(line_data.values()))
                waiting_times = [f"{bus['minutes']}'" for bus in first_destination[:2]]
                
                # Pad with "--" if we have less than 2 times
                while len(waiting_times) < 2:
                    waiting_times.append("--")

                bus_times.append({
                    "line": line,
                    "times": waiting_times
                })

            return bus_times, None  # None means no error message

        except requests.exceptions.ConnectionError:
            return self._get_error_data(), "Connection failed"
        except Exception as e:
            logger.error(f"Error fetching bus times: {e}")
            return self._get_error_data(), f"Error: {str(e)}"

    def _get_error_data(self) -> List[Dict]:
        """Return error data structure when something goes wrong"""
        return [
            {"line": "56", "times": ["--", "--"]},
            {"line": "59", "times": ["--", "--"]}
        ]

if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.DEBUG)
    bus_service = BusService()
    print(bus_service.get_waiting_times()) 