#!/usr/bin/env python3

'''
This file implements a WebSerial server that enables communication between a web interface and a Raspberry Pi device over USB serial.



Important: when adding new commands, also update the docs/setup/webserial_test.html file
'''

import serial
import time
import json
import logging
import select
from logging.handlers import RotatingFileHandler
from wifi_config import WiFiConfig
import logging
import log_config
from config_manager import ConfigManager
import os
import threading
import socket
import subprocess

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Set up logging
log_file = os.path.join(log_dir, 'webserial.log')
try:
    logging.basicConfig(
        handlers=[RotatingFileHandler(log_file, maxBytes=100000, backupCount=3)],
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(console_handler)
except Exception as e:
    # If we can't write to the log file, log to syslog
    import syslog
    syslog.syslog(syslog.LOG_ERR, f"Failed to setup file logging: {str(e)}")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

logger = logging.getLogger(__name__)
logger.info("WebSerial server starting up...")

class WebSerialServer:
    def __init__(self):
        self.serial_ports = {}  # Dictionary to hold multiple serial connections
        self.running = True
        self.wifi = WiFiConfig()
        self.config = ConfigManager()
        self.poll = select.poll()
        self.setup_serial_ports()

    def setup_serial_ports(self):
        """Initialize serial connections"""
        try:
            # Wait for USB Gadget Serial (up to 10 seconds)
            usb_connected = False
            for _ in range(10):
                if os.path.exists('/dev/ttyGS0'):
                    try:
                        # USB Gadget Serial
                        usb_serial = serial.Serial(
                            port='/dev/ttyGS0',  # USB gadget serial port
                            baudrate=115200,
                            bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE,
                            stopbits=serial.STOPBITS_ONE,
                            timeout=None,
                            xonxoff=False,
                            rtscts=False,
                            dsrdtr=False
                        )
                        self.serial_ports['usb'] = usb_serial
                        self.poll.register(usb_serial.fileno(), select.POLLIN)
                        logger.info("USB Serial connection established")
                        usb_connected = True
                        break
                    except Exception as e:
                        logger.error(f"Failed to open USB Serial port: {e}")
                        time.sleep(1)
                else:
                    logger.info("Waiting for /dev/ttyGS0...")
                    time.sleep(1)
            
            if not usb_connected:
                logger.error("USB Gadget device not found. Please ensure the USB gadget module is loaded.")
                # Try to load the module
                try:
                    subprocess.run(['sudo', 'modprobe', 'libcomposite'], check=True)
                    subprocess.run(['sudo', 'modprobe', 'usb_f_acm'], check=True)
                    logger.info("USB modules loaded, please wait for device to appear")
                except Exception as e:
                    logger.error(f"Failed to load USB modules: {e}")

            # Bluetooth Serial (if available)
            try:
                # Wait for rfcomm0 to be available (up to 5 seconds)
                for _ in range(5):
                    if os.path.exists('/dev/rfcomm0'):
                        break
                    logger.info("Waiting for /dev/rfcomm0...")
                    time.sleep(1)

                bt_serial = serial.Serial(
                    port='/dev/rfcomm0',  # Default Bluetooth serial port
                    baudrate=115200,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=None,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False
                )
                self.serial_ports['bluetooth'] = bt_serial
                self.poll.register(bt_serial.fileno(), select.POLLIN)
                logger.info("Bluetooth Serial connection established")
            except Exception as e:
                logger.info(f"Bluetooth Serial not available: {e}")

            # If no ports are available, raise an error
            if not self.serial_ports:
                raise Exception("No serial ports could be initialized")

        except Exception as e:
            logger.error(f"Failed to setup serial ports: {e}")
            # Don't raise the error, let the service continue running and retry later
            return False
        
        return True

    def get_local_ip(self):
        """Get the local IP address of the device"""
        try:
            # Get all network interfaces
            result = subprocess.run(
                ['ip', '-o', '-4', 'addr', 'list'],
                capture_output=True,
                text=True
            )
            
            # Look for wlan0 first (WiFi interface)
            for line in result.stdout.splitlines():
                if 'wlan0' in line:
                    # Extract IP address using string manipulation
                    # Format: 2: wlan0    inet 192.168.1.100/24 ...
                    ip = line.split()[3].split('/')[0]
                    return {'status': 'success', 'ip': ip}
            
            # If no WiFi, look for eth0 (Ethernet interface)
            for line in result.stdout.splitlines():
                if 'eth0' in line:
                    ip = line.split()[3].split('/')[0]
                    return {'status': 'success', 'ip': ip}
            
            return {'status': 'error', 'message': 'No suitable network interface found'}
            
        except Exception as e:
            logger.error(f"Error getting local IP: {e}")
            return {'status': 'error', 'message': str(e)}

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
            elif command == 'wifi_current':
                response = self.wifi.get_current_connection()
            elif command == 'get_ip':
                response = self.get_local_ip()
            elif command == 'config_get':
                value = self.config.get_value(
                    data.get('config_type'),
                    data.get('key')
                )
                response = {'status': 'success', 'value': value}
            elif command == 'config_set':
                success = self.config.set_value(
                    data.get('config_type'),
                    data.get('key'),
                    data.get('value')
                )
                response = {'status': 'success' if success else 'error'}
            elif command == 'config_read':
                verbose = data.get('verbose', False)
                content, variables = self.config.read_config(
                    data.get('config_type'),
                    verbose=verbose
                )
                response = {
                    'status': 'success',
                    'content': content,
                    'variables': variables
                }
            elif command == 'config_update':
                success = self.config.update_config(
                    data.get('config_type'),
                    data.get('content')
                )
                response = {'status': 'success' if success else 'error'}
            elif command == 'restart':
                # Send success response before initiating restart
                response = {'status': 'success', 'message': 'Restarting service...'}
                self.send_response(response)
                
                # Start delayed exit in separate thread
                logger.info("Restart requested, starting delayed exit thread")
                def delayed_exit():
                    logger.info("Initiating service restart...")
                    time.sleep(1)
                    logger.info("Forcing process exit...")
                    os._exit(1)  # Force exit the entire process
                
                exit_thread = threading.Thread(target=delayed_exit, daemon=False)
                exit_thread.start()
                return  # Return immediately as we've already sent the response
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
            for port in self.serial_ports.values():
                port.write(message.encode())
                port.flush()
            logger.debug(f"Sent response: {message.strip()}")
        except Exception as e:
            logger.error(f"Failed to send response: {e}")

    def run(self):
        """Main loop using poll()"""
        logger.info("Starting WebSerial server")
        
        while self.running:
            try:
                events = self.poll.poll(1000)  # 1000ms timeout
                
                for fd, event in events:
                    if event & select.POLLIN:
                        try:
                            # Find which port triggered the event
                            active_port = None
                            for port_type, port in self.serial_ports.items():
                                if port.fileno() == fd:
                                    active_port = port
                                    break

                            if not active_port:
                                continue

                            data = active_port.readline()
                            if not data:
                                logger.warning("No data received, attempting to reconnect...")
                                self.reconnect()
                                break
                            message = data.decode().strip()
                            logger.debug(f"Received: {message}")
                            self.handle_message(message)
                        except serial.SerialException as e:
                            logger.error(f"Serial error: {e}")
                            self.reconnect()
                            break
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(1)  # Prevent rapid error loops

    def reconnect(self):
        """Attempt to reconnect to the serial device"""
        try:
            logger.info("Attempting to reconnect...")
            for port in self.serial_ports.values():
                if port.is_open:
                    port.close()
            time.sleep(1)  # Wait before reconnecting
            self.setup_serial_ports()
            logger.info("Reconnected successfully")
        except Exception as e:
            logger.error(f"Failed to reconnect: {e}")
            time.sleep(5)  # Wait longer before next attempt

    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up...")
        self.running = False
        for port in self.serial_ports.values():
            if port.is_open:
                port.close()
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