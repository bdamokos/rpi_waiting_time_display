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
from threading import Lock
dotenv.load_dotenv(override=True)

DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))

class MockDisplay:
    """Mock display class for development without hardware"""
    def __init__(self):
        logger.warning("Using mock display - no actual hardware will be updated!")
        # Standard dimensions for 2.13inch display
        # Our script assumes the display is rotated 90 degrees so will swap width and height
        self.height = 250
        self.width = 120
        
        # Get mock display type from environment
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
        # Save the image for debugging
        DisplayAdapter.save_debug_image(image)
        return image

    def displayPartial(self, image):
        logger.debug("Mock: displayPartial() called")
        DisplayAdapter.save_debug_image(image)

    def displayPartBaseImage(self, image):
        logger.debug("Mock: displayPartBaseImage() called")
        DisplayAdapter.save_debug_image(image)

class DisplayAdapter:
    @staticmethod
    def save_debug_image(image):
        """Save a debug image of the current display buffer"""
        try:
            # Skip saving debug image if it's a bytearray
            if isinstance(image, bytearray):
                logger.debug("Skipping debug image save for bytearray buffer")
                return
            
            # Only try to save if it's a PIL Image
            if isinstance(image, Image.Image):
                # Rotate the image back to normal orientation
                image = image.rotate(-DISPLAY_SCREEN_ROTATION, expand=True)
                debug_path = "debug_output.png"
                image.save(debug_path)
                logger.info(f"Debug image saved to {debug_path}")
            else:
                logger.debug(f"Skipping debug image save for unsupported type: {type(image)}")
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
            
            # Add displayPartial support if available
            if hasattr(epd, 'displayPartial'):
                original_displayPartial = epd.displayPartial
                def displayPartial_wrapper(image):
                    try:
                        logger.debug("Using native displayPartial mode")
                        # Save debug image before converting to buffer
                        DisplayAdapter.save_debug_image(image)
                        # If image is already a bytearray, use it directly
                        if isinstance(image, bytearray):
                            return original_displayPartial(image)
                        # Otherwise convert to buffer
                        return original_displayPartial(epd.getbuffer(image))
                    except Exception as e:
                        logger.error(f"Error in displayPartial: {str(e)}\n{traceback.format_exc()}")
                        raise
                epd.displayPartial = displayPartial_wrapper
                
                # Also wrap displayPartBaseImage if available
                if hasattr(epd, 'displayPartBaseImage'):
                    original_displayPartBaseImage = epd.displayPartBaseImage
                    def displayPartBaseImage_wrapper(image):
                        try:
                            logger.debug("Using native displayPartBaseImage mode")
                            # Save debug image before converting to buffer
                            DisplayAdapter.save_debug_image(image)
                            # If image is already a bytearray, use it directly
                            if isinstance(image, bytearray):
                                return original_displayPartBaseImage(image)
                            # Otherwise convert to buffer
                            return original_displayPartBaseImage(epd.getbuffer(image))
                        except Exception as e:
                            logger.error(f"Error in displayPartBaseImage: {str(e)}\n{traceback.format_exc()}")
                            raise
                    epd.displayPartBaseImage = displayPartBaseImage_wrapper
            
            return epd
            
        except ImportError as e:
            logger.error(f"Could not import display module {display_model}: {str(e)}\n{traceback.format_exc()}")
            logger.warning("Falling back to mock display")
            return MockDisplay()
        except Exception as e:
            logger.error(f"Error creating display instance: {str(e)}\n{traceback.format_exc()}")
            raise

display_lock = Lock()  # Global lock for display operations
def return_display_lock():
    return display_lock

def display_full_refresh(epd):
    with display_lock:
        epd.init()
        epd.Clear()
        epd.init_Fast()


def initialize_display():
    epd = None
    with display_lock:
                # Initialize display using adapter
        logger.debug("About to initialize display")
        epd = DisplayAdapter.get_display()

        # Add debug logs before EPD commands
        logger.debug("About to call epd.init()")
        try:

            epd.init()
        except Exception as e:
            logger.error(f"Error initializing display: {str(e)}\n{traceback.format_exc()}")
            raise

        logger.debug("About to call epd.Clear()")
        try:

            epd.Clear()
        except Exception as e:
            logger.error(f"Error clearing display: {str(e)}\n{traceback.format_exc()}")
            raise
        logger.info("Display initialized")

        logger.debug("About to call epd.init_Fast()")

        epd.init_Fast()
        logger.info("Fast mode initialized")
    return epd

def display_cleanup(epd):
    with display_lock:
        epd.init()
        epd.Clear()
        epd.sleep()
        epd.epdconfig.module_exit(cleanup=True)
        logger.info("Display cleanup completed")

def init_partial_mode(epd, base_image):
    """Initialize partial mode with a base image.
    
    Args:
        epd: The display instance
        base_image: PIL Image to use as the base image
    """
    with display_lock:
        if not hasattr(epd, 'displayPartial'):
            logger.warning("Display does not support partial updates")
            return False
            
        try:
            epd.init()
            if hasattr(epd, 'displayPartBaseImage'):
                logger.debug("Setting base image for partial updates")
                base_buffer = epd.getbuffer(base_image)
                epd.displayPartBaseImage(base_buffer)
                return True
            else:
                logger.warning("Display does not support base image for partial updates")
                return False
        except Exception as e:
            logger.error(f"Error initializing partial mode: {e}")
            return False