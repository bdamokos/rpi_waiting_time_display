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
        DisplayAdapter.save_debug_image(image)
        return image

class DisplayAdapter:
    @staticmethod
    def save_debug_image(image):
        """Save a debug image of the current display buffer"""
        try:
            # Rotate the image back to normal orientation
            image = image.rotate(-90, expand=True)
            debug_path = "debug_output.png"
            image.save(debug_path)
            logger.info(f"Debug image saved to {debug_path}")
        except Exception as e:
            logger.error(f"Error saving debug image: {e}")
    
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
            
            # Add color constants if not defined
            if not hasattr(epd, 'BLACK'):
                logger.debug("Display does not define BLACK, using default value")
                epd.BLACK = 0x00  # For monochrome displays, 0 is typically black
            if not hasattr(epd, 'WHITE'):
                logger.debug("Display does not define WHITE, using default value")
                epd.WHITE = 0xFF  # For monochrome displays, 255 (0xFF) is typically white
            
            # Add color constants for compatibility with color displays
            if not hasattr(epd, 'RED'):
                logger.debug("Display does not support RED, falling back to BLACK")
                epd.RED = epd.BLACK
            if not hasattr(epd, 'YELLOW'):
                logger.debug("Display does not support YELLOW, falling back to BLACK")
                epd.YELLOW = epd.BLACK
            
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
            if not hasattr(epd, 'init_Fast'):
                # Check if the display has a native fast mode
                if hasattr(epd, 'init_fast'):
                    def init_Fast():
                        try:
                            logger.debug("Using native fast mode (init_fast)")
                            return epd.init_fast()
                        except Exception as e:
                            logger.error(f"Error in init_Fast: {str(e)}\n{traceback.format_exc()}")
                            raise
                    epd.init_Fast = init_Fast
                    
                    # Also wrap display method to use fast mode when available
                    if hasattr(epd, 'display_fast'):
                        original_display = epd.display
                        def display_wrapper(*args, **kwargs):
                            try:
                                logger.debug("Using native fast display mode")
                                return epd.display_fast(*args, **kwargs)
                            except Exception as e:
                                logger.error(f"Error in display_fast: {str(e)}\n{traceback.format_exc()}")
                                # Fall back to regular display if fast mode fails
                                logger.warning("Fast display failed, falling back to regular display")
                                return original_display(*args, **kwargs)
                        epd.display = display_wrapper
                elif hasattr(epd, 'display_fast'):
                    def init_Fast():
                        try:
                            logger.debug("Display has display_fast but no init_fast, using regular init")
                            return init_wrapper()
                        except Exception as e:
                            logger.error(f"Error in init_Fast: {str(e)}\n{traceback.format_exc()}")
                            raise
                    epd.init_Fast = init_Fast
                    
                    # Wrap display to use fast mode
                    original_display = epd.display
                    def display_wrapper(*args, **kwargs):
                        try:
                            logger.debug("Using native fast display mode")
                            return epd.display_fast(*args, **kwargs)
                        except Exception as e:
                            logger.error(f"Error in display_fast: {str(e)}\n{traceback.format_exc()}")
                            return original_display(*args, **kwargs)
                    epd.display = display_wrapper
                else:
                    # No native fast mode, fall back to partial update
                    def init_Fast():
                        try:
                            if hasattr(epd, 'lut_partial_update'):
                                logger.debug("Using lut_partial_update for init_Fast")
                                return init_wrapper(epd.lut_partial_update)
                            logger.debug("No fast mode available, using regular init")
                            return init_wrapper()
                        except Exception as e:
                            logger.error(f"Error in init_Fast: {str(e)}\n{traceback.format_exc()}")
                            raise
                    epd.init_Fast = init_Fast
            
            # Wrap the getbuffer method to save debug output
            original_getbuffer = epd.getbuffer
            def getbuffer_wrapper(image):
                DisplayAdapter.save_debug_image(image)
                return original_getbuffer(image)
            epd.getbuffer = getbuffer_wrapper
            
            return epd
            
        except ImportError as e:
            logger.error(f"Could not import display module {display_model}: {str(e)}\n{traceback.format_exc()}")
            logger.warning("Falling back to mock display")
            return MockDisplay()
        except Exception as e:
            logger.error(f"Error creating display instance: {str(e)}\n{traceback.format_exc()}")
            raise