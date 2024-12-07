import os
import time
import subprocess
from flask import Flask, request, redirect, url_for, Response
import logging 
import log_config
import dotenv
import platform
from PIL import Image, ImageDraw, ImageFont
import qrcode
logger = logging.getLogger(__name__)
dotenv.load_dotenv(override=True)
app = Flask(__name__)
HOTSPOT_ENABLED = os.getenv('hotspot_enabled', 'true').lower() == 'true'
HOTSPOT_SSID = os.getenv('hotspot_ssid', 'PiHotspot')
HOTSPOT_PASSWORD = os.getenv('hotspot_password', 'YourPassword')

def get_hostname():
    """Get the Pi's hostname with .local suffix."""
    try:
        # Get raw hostname
        hostname = subprocess.check_output(['hostname']).decode('utf-8').strip()
        # Return hostname with .local suffix
        return f"{hostname}.local"
    except Exception as e:
        logger.error(f"Error getting hostname: {e}")
        return "raspberrypi.local" # Default fallback

hostname = get_hostname()
DEBUG_SERVER_ENABLED = True if os.getenv("debug_server_enabled", "false").lower() == "true" else False
DEBUG_SERVER_PORT = int(os.getenv("debug_server_port", 5002))

def is_running_on_pi():
    """Check if we're running on a Raspberry Pi."""
    try:
        with open('/sys/firmware/devicetree/base/model', 'r') as f:
            return 'raspberry pi' in f.read().lower()
    except:
        return False

def cleanup_captive_portal():
    """Clean up captive portal configuration."""
    if not is_running_on_pi():
        return

    try:
        # Clear iptables rules and stop dnsmasq
        subprocess.run(['sudo', 'iptables', '-t', 'nat', '-F'], check=True)
        subprocess.run(['sudo', 'systemctl', 'stop', 'dnsmasq'], check=True)
        logger.info("Captive portal cleanup completed")
    except Exception as e:
        logger.error(f"Error cleaning up captive portal: {e}")

def is_connected():
    """Check if the Pi is connected to a Wi-Fi network."""
    if is_running_on_pi():
        try:
            # Original RPI/Linux logic
            result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'], capture_output=True, text=True)
            return 'yes' in result.stdout
        except Exception as e:
            logger.error(f"Error checking Wi-Fi connection: {e}")
            return False
    else:
        # Non-Pi environment (e.g., macOS) - use mock SSID
        mock_ssid = os.getenv('mock_connected_ssid', '')
        logger.info(f"Running on non-Pi system. Using mock SSID connection status: {bool(mock_ssid)}")
        return bool(mock_ssid)

def setup_captive_portal():
    """Configure the system for captive portal."""
    if not is_running_on_pi():
        logger.info("Not running on Pi - skipping captive portal setup")
        return

    try:
        subprocess.run(['sudo', '/usr/local/bin/wifi-portal-setup'], check=True)
        logger.info("Captive portal setup completed")
    except Exception as e:
        logger.error(f"Error setting up captive portal: {e}")

def create_hotspot():
    """Create a Wi-Fi hotspot using nmcli."""
    if not HOTSPOT_ENABLED:
        logger.info("Hotspot is not enabled in the .env file. Skipping hotspot creation.")
        return

    if is_running_on_pi():
        try:
            subprocess.run(['nmcli', 'dev', 'wifi', 'hotspot', 'ifname', 'wlan0', 'ssid', HOTSPOT_SSID, 'password', HOTSPOT_PASSWORD], check=True)
            logger.info(f"Hotspot '{HOTSPOT_SSID}' created.")
            setup_captive_portal()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create hotspot: {e}")
    else:
        logger.info(f"Not running on a Raspberry Pi. Skipping hotspot creation.")

# Add new routes for captive portal detection
@app.route('/generate_204')  # Android
@app.route('/ncsi.txt')      # Windows
@app.route('/hotspot-detect.html')  # iOS
@app.route('/library/test/success.html')  # iOS
@app.route('/connecttest.txt')  # Windows
def captive_portal_check():
    """Handle captive portal detection requests."""
    return redirect(url_for('wifi_setup'))

@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests."""
    return Response(status=204)

@app.route('/', methods=['GET', 'POST'])
def wifi_setup():
    """Web interface for setting up Wi-Fi credentials."""
    if request.method == 'POST':
        ssid = request.form.get('ssid')
        password = request.form.get('password')
        if ssid and password:
            try:
                subprocess.run(['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password], check=True)
                logger.info(f"Connected to {ssid}. Restarting...")
                # Clean up captive portal before reboot
                cleanup_captive_portal()
                os.system('reboot')
            except subprocess.CalledProcessError as e:
                return f"Failed to connect to {ssid}: {e}", 500
        return redirect(url_for('wifi_setup'))

    return f'''
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ 
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                input, label {{ 
                    display: block;
                    margin: 10px 0;
                    width: 100%;
                }}
                input[type="text"], input[type="password"] {{
                    padding: 8px;
                    margin: 5px 0 20px 0;
                }}
                input[type="submit"] {{
                    background-color: #4CAF50;
                    color: white;
                    padding: 14px 20px;
                    border: none;
                    cursor: pointer;
                }}
                input[type="submit"]:hover {{
                    background-color: #45a049;
                }}
            </style>
        </head>
        <body>
            <h1>Wi-Fi Setup</h1>
            <form method="post">
                <label for="ssid">Network Name (SSID):</label>
                <input type="text" id="ssid" name="ssid" required>
                
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
                
                <input type="submit" value="Connect">
            </form>
            
            <p>Once connected, the device will restart and connect to your Wi-Fi network.</p>
            <p>You can then access it at: <a href="http://{hostname}">http://{hostname}</a></p>
            
            {f'<p>Debug server available at: <a href="http://{hostname}:{DEBUG_SERVER_PORT}">http://{hostname}:{DEBUG_SERVER_PORT}</a></p>' if DEBUG_SERVER_ENABLED else ''}
        </body>
    </html>
    '''

def main():
    try:
        while True:
            if not is_connected():
                print("Not connected to Wi-Fi. Setting up hotspot...")
                create_hotspot()
                # Ensure debug mode is off in production
                app.run(host='0.0.0.0', port=80, debug=False)
            else:
                print("Connected to Wi-Fi.")
            time.sleep(900)  # Check every 15 minutes
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        cleanup_captive_portal()
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        cleanup_captive_portal()

def show_no_wifi_display(epd):
    """Display a Wi-Fi QR code and no Wi-Fi symbol on the screen."""
    Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
    draw = ImageDraw.Draw(Himage)
    
    try:
        font_tiny = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 8)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 16)
    except:
        font_medium = ImageFont.load_default()
        font_tiny = font_medium

    MARGIN = 8
    
    # Split the message into multiple lines
    message_lines = [
        f"No Wi-Fi connection. Please connect to:",
        f"SSID: {HOTSPOT_SSID}",
        f"Password: {HOTSPOT_PASSWORD}"
    ]

    # Calculate total text height
    line_spacing = 4
    total_text_height = sum(draw.textbbox((0, 0), line, font=font_tiny)[3] - draw.textbbox((0, 0), line, font=font_tiny)[1] for line in message_lines) + (line_spacing * (len(message_lines) - 1))

    # Generate smaller QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=2,
        border=1,
    )
    wifi_qr_data = f"WIFI:S:{HOTSPOT_SSID};T:WPA;P:{HOTSPOT_PASSWORD};;"
    qr.add_data(wifi_qr_data)
    qr.make(fit=True)

    # Create and resize QR code
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')
    qr_size = min(70, Himage.width - (2 * MARGIN))  # Smaller QR code
    qr_img = qr_img.resize((qr_size, qr_size))

    # Calculate vertical positions
    total_content_height = total_text_height + qr_size + MARGIN
    start_y = (Himage.height - total_content_height) // 2

    # Draw text lines
    current_y = start_y
    for line in message_lines:
        bbox = draw.textbbox((0, 0), line, font=font_tiny)
        text_width = bbox[2] - bbox[0]
        x = (Himage.width - text_width) // 2
        draw.text((x, current_y), line, font=font_tiny, fill=epd.BLACK)
        current_y += bbox[3] - bbox[1] + line_spacing

    # Draw QR code below text
    qr_x = (Himage.width - qr_size) // 2
    qr_y = current_y + MARGIN
    Himage.paste(qr_img, (qr_x, qr_y))

    # Draw a border around the display
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=epd.BLACK)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(90, expand=True)
    
    # Display the image
    buffer = epd.getbuffer(Himage)
    epd.display(buffer)

if __name__ == '__main__':
    main()