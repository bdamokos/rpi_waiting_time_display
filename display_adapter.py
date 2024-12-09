import logging
import log_config
import importlib
import os
from PIL import Image
import dotenv
import inspect
import traceback
logger = logging.getLogger(__name__)
import dotenv
import os

dotenv.load_dotenv(override=true)

DISPLAY_SCREEN_ROTATION = os.getenv('screen_rotation', 90)

class MockDisplay:
    """Mock display class for development without hardware"""
    def __init__(self):
        logger.warning("Using mock display - no actual hardware will be updated!")
        # Standard dimensions for 2.13inch display
        # Our script assumes the display is rotated 90 degrees so will swap width and height
        self.height = 250
        self.width = 120
        
        # Get mock display type from environment
        dotenv.load_dotenv(override=True)
        self.mock_display_type = os.getenv('mock_display_type', 'bw').lower()
        
        # Standard colors
        self.BLACK = (0, 0, 0)
        self.WHITE = (255, 255, 255)
        
        # Add color support based on mock_display_type
        if self.mock_display_type != 'bw':
            self.RED = (255, 0, 0)
            self.YELLOW = (255, 255, 0)
            logger.info("Mock display initialized in color mode")
        else:
            logger.info("Mock display initialized in B&W mode")
        
        # Set display type flag
        self.is_bw_display = self.mock_display_type == 'bw'
        
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
        # Convert image to appropriate mode based on display type
        if self.is_bw_display:
            image = image.convert('1')  # Convert to 1-bit B&W
            logger.debug("Mock: Converting image to B&W mode")
        else:
            image = image.convert('RGB')  # Keep color information
            logger.debug("Mock: Keeping color information")
        
        # Save the image for debugging
        DisplayAdapter.save_debug_image(image)
        return image

class DisplayAdapter:
    @staticmethod
    def save_debug_image(image):
        """Save a debug image of the current display buffer"""
        try:
            # Rotate the image back to normal orientation
            image = image.rotate(-DISPLAY_SCREEN_ROTATION, expand=True)
            debug_path = "debug_output.png"
            image.save(debug_path)
            logger.info(f"Debug image saved to {debug_path}")
        except Exception as e:
            logger.error(f"Error saving debug image: {e}")
    
    @staticmethod
    def _get_available_colors(epd):
        """Helper function to get available colors for the display"""
        colors = {
            'black': (getattr(epd, 'BLACK', 0x000000), (0, 0, 0)),
            'white': (getattr(epd, 'WHITE', 0xffffff), (255, 255, 255))
        }
        
        # Debug what the display actually has
        logger.debug(f"Display color values - BLACK: {epd.BLACK}, WHITE: {epd.WHITE}")
        if hasattr(epd, 'RED') and epd.RED != epd.BLACK and epd.RED != 0x00:
            colors['red'] = (epd.RED, (255, 0, 0))
            logger.debug(f"Display has RED support: {epd.RED}")
        if hasattr(epd, 'YELLOW') and epd.YELLOW != epd.BLACK and epd.YELLOW != 0x00:
            colors['yellow'] = (epd.YELLOW, (255, 255, 0))
            logger.debug(f"Display has YELLOW support: {epd.YELLOW}")
        
        # Set display type based on available colors
        epd.is_bw_display = len(colors) == 2  # Only black and white available
        logger.debug(f"Display type: {'Black & White' if epd.is_bw_display else 'Color'} ({len(colors)} colors)")
        
        return colors

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
            
            # Initialize color support and detect display type
            DisplayAdapter._get_available_colors(epd)
            
            # Wrap getbuffer method to handle different image formats
            original_getbuffer = epd.getbuffer
            def getbuffer_wrapper(image):
                # Convert to 1-bit if it's a B&W display
                if epd.is_bw_display:
                    logger.debug("Converting image to 1-bit for B&W display")
                    image = image.convert('1')
                DisplayAdapter.save_debug_image(image)
                return original_getbuffer(image)
            epd.getbuffer = getbuffer_wrapper
            
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
            
            return epd
            
        except ImportError as e:
            logger.error(f"Could not import display module {display_model}: {str(e)}\n{traceback.format_exc()}")
            logger.warning("Falling back to mock display")
            return MockDisplay()
        except Exception as e:
            logger.error(f"Error creating display instance: {str(e)}\n{traceback.format_exc()}")
            raise