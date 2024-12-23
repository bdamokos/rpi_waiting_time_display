import pytest
from PIL import Image
from display_adapter import DisplayAdapter, MockDisplay, return_display_lock
from unittest.mock import patch, MagicMock
from threading import Lock
import os

@pytest.fixture
def mock_display():
    """Fixture providing a MockDisplay instance"""
    return MockDisplay()

@pytest.fixture
def display_adapter():
    """Fixture providing a DisplayAdapter instance"""
    return DisplayAdapter()

def test_mock_display_initialization():
    """Test MockDisplay initialization with different configurations"""
    # Test B&W display
    with patch.dict(os.environ, {'mock_display_type': 'bw'}, clear=True):
        display = MockDisplay()
        assert display.mock_display_type == 'bw'
        assert display.is_bw_display is True
        assert hasattr(display, 'BLACK')
        assert hasattr(display, 'WHITE')
        assert not hasattr(display, 'RED')
        assert not hasattr(display, 'YELLOW')
        assert display.width == 120
        assert display.height == 250

    # Test color display
    with patch.dict(os.environ, {'mock_display_type': 'color'}, clear=True):
        display = MockDisplay()
        assert display.mock_display_type == 'color'
        assert display.is_bw_display is False
        assert hasattr(display, 'BLACK')
        assert hasattr(display, 'WHITE')
        assert hasattr(display, 'RED')
        assert hasattr(display, 'YELLOW')

def test_mock_display_methods(mock_display):
    """Test MockDisplay basic methods"""
    # Test initialization methods
    assert mock_display.init() is None
    assert mock_display.init_Fast() is None
    assert mock_display.Clear() is None
    assert mock_display.sleep() is None

    # Test display method
    test_image = Image.new('RGB', (mock_display.width, mock_display.height), color='white')
    assert mock_display.display(test_image) is None

def test_display_adapter_save_debug_image(display_adapter, tmp_path):
    """Test saving debug image"""
    test_image = Image.new('RGB', (120, 250), color='white')
    
    # Temporarily patch the save method to verify it's called
    with patch.object(Image.Image, 'save') as mock_save:
        DisplayAdapter.save_debug_image(test_image)
        mock_save.assert_called_once()

def test_display_adapter_get_available_colors(mock_display):
    """Test getting available colors for different display types"""
    # Test B&W display
    with patch.dict(os.environ, {'mock_display_type': 'bw'}, clear=True):
        display = MockDisplay()
        colors = DisplayAdapter._get_available_colors(display)
        assert len(colors) == 2  # BLACK and WHITE
        assert 'black' in colors
        assert 'white' in colors

    # Test color display
    with patch.dict(os.environ, {'mock_display_type': 'color'}, clear=True):
        display = MockDisplay()
        colors = DisplayAdapter._get_available_colors(display)
        assert len(colors) == 4  # BLACK, WHITE, RED, YELLOW
        assert 'black' in colors
        assert 'white' in colors
        assert 'red' in colors
        assert 'yellow' in colors

def test_display_lock():
    """Test display lock functionality"""
    lock = return_display_lock()
    assert lock is not None
    assert isinstance(lock, Lock)
    
    # Test that the same lock is returned on subsequent calls
    lock2 = return_display_lock()
    assert lock is lock2

@patch('display_adapter.importlib.import_module')
def test_get_display_hardware_import_error(mock_import):
    """Test display initialization with hardware import error"""
    mock_import.side_effect = ImportError("No module named 'waveshare_epd'")
    
    display = DisplayAdapter.get_display()
    assert isinstance(display, MockDisplay)

def test_getbuffer_wrapper(mock_display):
    """Test image buffer conversion"""
    # Create a test image
    test_image = Image.new('RGB', (mock_display.width, mock_display.height), color='white')
    
    # Get buffer
    buffer = mock_display.getbuffer(test_image)
    assert buffer is not None
    
    # For B&W display, should convert to 1-bit
    if mock_display.is_bw_display:
        assert isinstance(buffer, Image.Image)
        assert buffer.mode in ['1', 'L']