import PIL
import weather
import logging
import log_config
from PIL import Image, ImageDraw, ImageFont
from weather import WeatherService
import qrcode
from datetime import datetime
import os

logger = logging.getLogger(__name__)

width = 250
height = 122
url_for_qr_code = "http://raspberrypi.local:5001"
available_colors = ['black', 'white', 'red', 'yellow']
WEATHER_ICONS = {
    'Clear': '☀',
    'Clouds': '☁',
    'Rain': '🌧',
    'Snow': '❄',
    'Thunderstorm': '⚡',
    'Drizzle': '🌦',
    'Mist': '🌫',
}

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Initialize weather service
weather_service = WeatherService()
weather_data = weather_service.get_detailed_weather()

# Create a new image with the specified width and height
image = Image.new('RGB', (width, height), 'white')
draw = ImageDraw.Draw(image)

# Font paths for different operating systems
font_paths = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
    "/System/Library/Fonts/DejaVuSans.ttf",  # macOS
    "C:\\Windows\\Fonts\\DejaVuSans.ttf",  # Windows
    os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),  # Local fonts directory
]

# Try to load DejaVu Sans font
font_large = font = font_small = None
for font_path in font_paths:
    try:
        if os.path.exists(font_path):
            font_large = ImageFont.truetype(font_path, 32)  # For temperature
            font = ImageFont.truetype(font_path, 14)  # For normal text
            font_small = ImageFont.truetype(font_path, 10)  # For small text
            logger.info(f"Loaded font from {font_path}")
            break
    except Exception as e:
        logger.warning(f"Could not load font from {font_path}: {e}")

if font_large is None:
    logger.warning("DejaVu Sans font not found, using default font")
    font_large = font = font_small = ImageFont.load_default()

def draw_box(x, y, w, h, text, fill='black', font_size='normal', multiline_align='center'):
    # Draw box
    draw.rectangle([x, y, x + w - 1, y + h - 1], outline='black')
    
    # Select font based on size parameter
    if font_size == 'large':
        selected_font = font_large
    elif font_size == 'small':
        selected_font = font_small
    else:
        selected_font = font
    
    # Calculate text position to center it
    lines = text.split('\n')
    line_heights = [draw.textbbox((0, 0), line, font=selected_font)[3] - draw.textbbox((0, 0), line, font=selected_font)[1] for line in lines]
    total_text_height = sum(line_heights) + (len(lines) - 1) * 2  # 2 pixels between lines
    
    if multiline_align == 'center':
        y_start = y + (h - total_text_height) // 2
    else:  # top alignment
        y_start = y + 2  # 2 pixels padding from top
    
    current_y = y_start
    for i, line in enumerate(lines):
        text_bbox = draw.textbbox((0, 0), line, font=selected_font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = x + (w - text_width) // 2
        draw.text((text_x, current_y), line, font=selected_font, fill=fill)
        current_y += line_heights[i] + 2  # 2 pixels between lines

# Generate QR code
qr = qrcode.QRCode(version=1, box_size=2, border=0)
qr.add_data(url_for_qr_code)
qr.make(fit=True)
qr_image = qr.make_image(fill_color="black", back_color="white")

# Calculate QR code position and size
qr_x = 200
qr_y = 20
qr_size = 40
qr_image = qr_image.resize((qr_size, qr_size))
image.paste(qr_image, (qr_x, qr_y, qr_x + qr_size, qr_y + qr_size))

# Get weather icon
current_condition = weather_data['current']['description']
weather_icon = WEATHER_ICONS.get(current_condition, '☀')  # Default to sun if condition not found

# Format forecast text for next 3 days
forecast_lines = []
for forecast in weather_data['forecasts']:
    icon = WEATHER_ICONS.get(forecast['condition'], '☀')
    forecast_lines.append(f"{icon}▼{forecast['min']}° ▲{forecast['max']}°")
forecast_text = " ".join(forecast_lines)

# Draw the grid sections
draw_box(0, 0, 80, 80, f"{weather_icon} {weather_data['current']['temperature']}°", font_size='large')
draw_box(80, 0, 60, 80, f"Feels\nlike:\n{weather_data['current']['feels_like']}°", font_size='small')
draw_box(140, 0, 60, 80, f"▼{weather_data['tomorrow']['min']}°\n▲{weather_data['tomorrow']['max']}°", font_size='normal')
draw_box(0, 80, 40, 40, f"↓\n{weather_data['sunset']}", font_size='small')
draw_box(40, 80, 60, 40, f"AQI: {weather_data['tomorrow']['air_quality']['aqi']}\n{weather_data['tomorrow']['air_quality']['aqi_label']}", font_size='small')
draw_box(100, 80, 100, 40, forecast_text, font_size='small')
draw_box(200, 80, 50, 40, f"{datetime.now().strftime('%H:%M')}", font_size='small')

# Save the image
image.save('weather_display.png')