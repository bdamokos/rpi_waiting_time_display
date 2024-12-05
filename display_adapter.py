import logging
import log_config
import importlib
import os
from PIL import Image
import dotenv
import inspect
import traceback
logger = logging.getLogger(__name__)

class MockDisplay:
    """Mock display class for development without hardware"""
    def __init__(self):
        logger.warning("Using mock display - no actual hardware will be updated!")
        # Standard dimensions for 2.13inch display
        # Our script assumes the display is rotated 90 degrees so will swap width and height
        self.height = 250
        self.width = 120
        
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
        #rotate the image back to normal
        image = image.rotate(-90, expand=True)
        debug_path = "debug_output.png"
        image.save(debug_path)
        logger.info(f"Debug image saved to {debug_path}")
        return image

class DisplayAdapter:
    @staticmethod
    def get_display():
        """Get the appropriate display instance based on environment"""
        dotenv.load_dotenv(override=True)
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
                
            # Add wrapper for init method to handle different signatures
            original_init = epd.init
            def init_wrapper(*args, **kwargs):
                try:
                    # Get the parameters of the original init method
                    sig = inspect.signature(original_init)
                    
                    # If no arguments provided but the original method requires them
                    if len(sig.parameters) > 1 and not args and not kwargs:
                        # For epd2in13, provide the lut_full_update as default
                        if hasattr(epd, 'lut_full_update'):
                            logger.debug(f"Using lut_full_update for init. Params: {sig.parameters}")
                            return original_init(epd.lut_full_update)
                        return original_init()
                    
                    # Call with original arguments
                    logger.debug(f"Calling init with args: {args}, kwargs: {kwargs}")
                    return original_init(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in init_wrapper: {str(e)}\n{traceback.format_exc()}")
                    raise
            
            epd.init = init_wrapper
            
            # Add fast mode methods if they don't exist
            if not hasattr(epd, 'init_Fast') and not hasattr(epd, 'init_fast'):
                # Check if the display has a native fast mode
                if hasattr(epd, 'display_fast'):
                    def init_Fast():
                        try:
                            # Use native fast init if available
                            if hasattr(epd, 'init_fast'):
                                return epd.init_fast()
                            # Otherwise use regular init
                            return init_wrapper()
                        except Exception as e:
                            logger.error(f"Error in init_Fast: {str(e)}\n{traceback.format_exc()}")
                            raise
                    epd.init_Fast = init_Fast
                    
                    # Also wrap display method to use fast mode when available
                    original_display = epd.display
                    def display_wrapper(*args, **kwargs):
                        try:
                            if hasattr(epd, 'display_fast'):
                                return epd.display_fast(*args, **kwargs)
                            return original_display(*args, **kwargs)
                        except Exception as e:
                            logger.error(f"Error in display: {str(e)}\n{traceback.format_exc()}")
                            raise
                    epd.display = display_wrapper
                else:
                    # Fall back to partial update if available
                    def init_Fast():
                        try:
                            if hasattr(epd, 'lut_partial_update'):
                                logger.debug("Using lut_partial_update for init_Fast")
                                return init_wrapper(epd.lut_partial_update)
                            return init_wrapper()
                        except Exception as e:
                            logger.error(f"Error in init_Fast: {str(e)}\n{traceback.format_exc()}")
                            raise
                    epd.init_Fast = init_Fast
            
            return epd
            
        except ImportError as e:
            logger.error(f"Could not import display module {display_model}: {str(e)}\n{traceback.format_exc()}")
            logger.warning("Falling back to mock display")
            return MockDisplay()
        except Exception as e:
            logger.error(f"Error creating display instance: {str(e)}\n{traceback.format_exc()}")
            raise 