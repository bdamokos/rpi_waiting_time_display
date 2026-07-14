import os
import logging
from logging.handlers import RotatingFileHandler


def configured_log_level(value=None):
    """Return a safe logging level for the display's constrained runtime."""
    name = (value or os.getenv("display_log_level", "INFO")).strip().upper()
    level = getattr(logging, name, None)
    return level if isinstance(level, int) else logging.INFO


# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.expanduser('~'), 'display_programme/logs')
os.makedirs(logs_dir, exist_ok=True)

# Set up root logger
logger = logging.getLogger()
log_level = configured_log_level()
logger.setLevel(log_level)

# Create formatters
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Rotating file handler
file_handler = RotatingFileHandler(
    os.path.join(logs_dir, 'app.log'),
    maxBytes=1024 * 1024,  # 1MB
    backupCount=5
)
file_handler.setLevel(log_level)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)
