#!/usr/bin/env python3
import os
import json
import logging
from pathlib import Path
import dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebUSBServer:
    """Server that handles WebUSB communication for device configuration"""
    
    def __init__(self):
        self.env_path = Path.home() / 'display_programme' / '.env'
        self.env_example_path = Path.home() / 'display_programme' / '.env.example'
        
    def get_config(self):
        """Get current configuration from .env file"""
        try:
            if not self.env_path.exists():
                # If .env doesn't exist, copy from example
                if self.env_example_path.exists():
                    self.env_path.write_text(self.env_example_path.read_text())
                else:
                    return {"error": "No configuration file found"}
            
            # Load current configuration
            config = {}
            dotenv.load_dotenv(self.env_path)
            for key, value in os.environ.items():
                if not key.startswith('_'):  # Skip internal variables
                    config[key] = value
            return config
            
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return {"error": str(e)}
    
    def save_config(self, config):
        """Save configuration to .env file"""
        try:
            # Create backup
            if self.env_path.exists():
                backup_path = self.env_path.with_suffix('.env.backup')
                self.env_path.rename(backup_path)
            
            # Write new configuration
            with open(self.env_path, 'w') as f:
                for key, value in config.items():
                    if not key.startswith('_'):  # Skip internal variables
                        f.write(f"{key}={value}\n")
            
            return {"status": "success"}
            
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return {"error": str(e)}
    
    def handle_command(self, command, data=None):
        """Handle incoming USB commands"""
        try:
            if command == 0x01:  # GET_CONFIG
                return json.dumps(self.get_config())
                
            elif command == 0x02:  # SAVE_CONFIG
                if not data:
                    return json.dumps({"error": "No configuration data provided"})
                config = json.loads(data)
                return json.dumps(self.save_config(config))
                
            else:
                return json.dumps({"error": f"Unknown command: {command}"})
                
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            return json.dumps({"error": str(e)})

def main():
    """Main function to start the WebUSB server"""
    try:
        server = WebUSBServer()
        logger.info("WebUSB server started")
        
        # TODO: Implement USB communication loop
        # This will be implemented based on the specific USB gadget driver
        
    except Exception as e:
        logger.error(f"Server error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 