import logging
import log_config
import importlib
import os
from PIL import Image

logger = logging.getLogger(__name__)

class MockDisplay:
    """Mock display class for development without hardware"""
    def __init__(self):
        logger.warning("Using mock display - no actual hardware will be updated!")
        # Standard dimensions for 2.13inch display
        self.height = 120
        self.width = 250
        
        # Standard colors
        self.BLACK = (0, 0, 0)
        self.WHITE = (255, 255, 255)
        self.RED = (255, 0, 0)
        self.YELLOW = (255, 255, 0)
        
        # Add mock epdconfig
        self.epdconfig = self.MockEPDConfig()
    
    class MockEPDConfig:
        @staticmethod
        def module_exit(cleanup=True):
            logger.debug(f"Mock: module_exit() called with cleanup={cleanup}")
    
    def init(self):
        logger.debug("Mock: init() called")
        
    def init_Fast(self):
        logger.debug("Mock: init_Fast() called")
    
    def Clear(self):
        logger.debug("Mock: Clear() called")
    
    def display(self, *args):
        logger.debug("Mock: display() called")
    
    def sleep(self):
        logger.debug("Mock: sleep() called")
    
    def getbuffer(self, image):
        logger.debug("Mock: getbuffer() called")
        # Save the image for debugging
        debug_path = "debug_output.png"
        image.save(debug_path)
        logger.info(f"Debug image saved to {debug_path}")
        return image

class DisplayAdapter:
    @staticmethod
    def get_display():
        """Get the appropriate display instance based on environment"""
        display_model = os.getenv('display_model')
        
        if not display_model:
            logger.warning("No display_model specified in environment variables")
            return MockDisplay()
            
        try:
            # Try to import the specified display module
            display_module = importlib.import_module(f"waveshare_epd.{display_model}")
            logger.info(f"Successfully loaded display module: {display_model}")
            
            # Create EPD instance
            epd = display_module.EPD()
            
            # Attach the epdconfig module to the instance if it doesn't already have it
            if not hasattr(epd, 'epdconfig'):
                epd.epdconfig = display_module.epdconfig
                
            return epd
            
        except ImportError as e:
            logger.warning(f"Could not import display module {display_model}: {e}")
            logger.warning("Falling back to mock display")
            return MockDisplay() 