#!/usr/bin/env python3
import serial
import time
import json
import logging
import select
from logging.handlers import RotatingFileHandler
from wifi_config import WiFiConfig
import logging
import log_config

# Set up logging
logging.basicConfig(
    handlers=[RotatingFileHandler('/home/bence/display_programme/logs/webserial.log', maxBytes=100000, backupCount=3)],
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# Add console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


logger = logging.getLogger(__name__)

class WebSerialServer:
    def __init__(self):
        self.ser = None
        self.running = True
        self.wifi = WiFiConfig()
        self.setup_serial()
        self.poll = select.poll()
        self.poll.register(self.ser.fileno(), select.POLLIN)

    def setup_serial(self):
        """Initialize serial connection"""
        try:
            self.ser = serial.Serial(
                port='/dev/ttyGS0',
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=None,  # Changed to None for blocking mode
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            logger.info("Serial connection established")
        except Exception as e:
            logger.error(f"Failed to setup serial: {e}")
            raise

    def handle_message(self, message):
        """Handle incoming messages"""
        try:
            # Try to parse as JSON
            data = json.loads(message)
            command = data.get('command')
            
            if command == 'wifi_scan':
                response = self.wifi.get_available_networks()
            elif command == 'wifi_saved':
                response = self.wifi.get_saved_networks()
            elif command == 'wifi_connect':
                response = self.wifi.connect_to_network(
                    data.get('ssid'),
                    data.get('password')
                )
            elif command == 'wifi_forget':
                response = self.wifi.forget_network(data.get('uuid'))
            elif command == 'basic_setup':
                response = self.handle_basic_setup(data)
            elif command == 'transit_setup':
                response = self.handle_transit_setup(data)
            elif command == 'weather_setup':
                response = self.handle_weather_setup(data)
            else:
                response = {'status': 'error', 'message': 'Unknown command'}
            
            # Send response
            self.send_response(response)
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {message}")
            self.send_response({'status': 'error', 'message': 'Invalid JSON'})
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            self.send_response({'status': 'error', 'message': str(e)})

    def handle_basic_setup(self, data):
        """Handle basic setup commands"""
        logger.info("Processing basic setup")
        # TODO: Implement basic setup
        return {'status': 'success', 'message': 'Basic setup processed'}

    def handle_transit_setup(self, data):
        """Handle transit setup commands"""
        logger.info("Processing transit setup")
        # TODO: Implement transit setup
        return {'status': 'success', 'message': 'Transit setup processed'}

    def handle_weather_setup(self, data):
        """Handle weather setup commands"""
        logger.info("Processing weather setup")
        # TODO: Implement weather setup
        return {'status': 'success', 'message': 'Weather setup processed'}

    def send_response(self, response):
        """Send response back through serial"""
        try:
            message = json.dumps(response) + '\n'
            self.ser.write(message.encode())
            self.ser.flush()
            logger.debug(f"Sent response: {message.strip()}")
        except Exception as e:
            logger.error(f"Failed to send response: {e}")

    def run(self):
        """Main loop using poll()"""
        logger.info("Starting WebSerial server")
        
        while self.running:
            try:
                # Wait for data with a 1-second timeout
                events = self.poll.poll(1000)  # 1000ms timeout
                
                for fd, event in events:
                    if event & select.POLLIN:
                        data = self.ser.readline()
                        message = data.decode().strip()
                        logger.debug(f"Received: {message}")
                        self.handle_message(message)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(1)  # Prevent rapid error loops

    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up...")
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        logger.info("Cleanup complete")

if __name__ == "__main__":
    server = WebSerialServer()
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        server.cleanup() 