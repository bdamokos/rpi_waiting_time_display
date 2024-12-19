#!/usr/bin/env python3
import subprocess
import logging
import json
import os

logger = logging.getLogger(__name__)

class WiFiConfig:
    """Handles WiFi configuration commands for WebUSB interface"""
    
    def __init__(self):
        self.nmcli_available = self._check_nmcli()
    
    def _check_nmcli(self):
        """Check if nmcli is available"""
        try:
            subprocess.run(['which', 'nmcli'], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            logger.warning("nmcli not found. WiFi configuration will be limited.")
            return False
    
    def get_available_networks(self):
        """Get list of available WiFi networks"""
        if not self.nmcli_available:
            return {"error": "nmcli not available"}
        
        try:
            # Force English language output
            env = os.environ.copy()
            env['LC_ALL'] = 'C'
            
            result = subprocess.run(
                ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
                capture_output=True,
                text=True,
                env=env
            )
            
            networks = []
            for line in result.stdout.splitlines():
                if line:
                    ssid, signal, security = line.split(':')
                    if ssid:  # Skip empty SSIDs
                        networks.append({
                            'ssid': ssid,
                            'signal': int(signal) if signal.isdigit() else 0,
                            'security': security != ''
                        })
            
            # Sort by signal strength
            networks.sort(key=lambda x: x['signal'], reverse=True)
            return {'networks': networks}
            
        except Exception as e:
            logger.error(f"Error getting WiFi networks: {e}")
            return {"error": str(e)}
    
    def connect_to_network(self, ssid, password=None):
        """Connect to a WiFi network"""
        if not self.nmcli_available:
            return {"error": "nmcli not available"}
        
        try:
            cmd = ['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid]
            if password:
                cmd.extend(['password', password])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return {"status": "success", "message": f"Connected to {ssid}"}
            else:
                return {"error": f"Failed to connect: {result.stderr}"}
                
        except Exception as e:
            logger.error(f"Error connecting to network: {e}")
            return {"error": str(e)}
    
    def get_saved_networks(self):
        """Get list of saved WiFi networks"""
        if not self.nmcli_available:
            return {"error": "nmcli not available"}
        
        try:
            env = os.environ.copy()
            env['LC_ALL'] = 'C'
            
            result = subprocess.run(
                ['sudo', 'nmcli', '-t', '-f', 'NAME,UUID,TYPE', 'connection', 'show'],
                capture_output=True,
                text=True,
                env=env
            )
            
            networks = []
            for line in result.stdout.splitlines():
                name, uuid, conn_type = line.split(':')
                if conn_type == '802-11-wireless':
                    networks.append({
                        'ssid': name,
                        'uuid': uuid
                    })
            
            return {'saved_networks': networks}
            
        except Exception as e:
            logger.error(f"Error getting saved networks: {e}")
            return {"error": str(e)}
    
    def forget_network(self, uuid):
        """Remove a saved WiFi network"""
        if not self.nmcli_available:
            return {"error": "nmcli not available"}
        
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', 'connection', 'delete', uuid],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return {"status": "success", "message": f"Removed network {uuid}"}
            else:
                return {"error": f"Failed to remove network: {result.stderr}"}
                
        except Exception as e:
            logger.error(f"Error removing network: {e}")
            return {"error": str(e)}

# Command handlers for WebUSB server
def handle_wifi_command(command, data=None):
    """Handle WiFi-related WebUSB commands"""
    wifi = WiFiConfig()
    
    try:
        if command == 0x10:  # GET_AVAILABLE_NETWORKS
            return json.dumps(wifi.get_available_networks())
            
        elif command == 0x11:  # GET_SAVED_NETWORKS
            return json.dumps(wifi.get_saved_networks())
            
        elif command == 0x12:  # CONNECT_TO_NETWORK
            if not data:
                return json.dumps({"error": "No network data provided"})
            network_data = json.loads(data)
            return json.dumps(wifi.connect_to_network(
                network_data.get('ssid'),
                network_data.get('password')
            ))
            
        elif command == 0x13:  # FORGET_NETWORK
            if not data:
                return json.dumps({"error": "No network UUID provided"})
            network_data = json.loads(data)
            return json.dumps(wifi.forget_network(network_data.get('uuid')))
            
        else:
            return json.dumps({"error": f"Unknown WiFi command: {command}"})
            
    except Exception as e:
        logger.error(f"Error handling WiFi command {command}: {e}")
        return json.dumps({"error": str(e)}) 