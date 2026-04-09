import logging
from logging.handlers import RotatingFileHandler
import os

class GuildLoggerAdapter(logging.LoggerAdapter):
    """Custom adapter to prefix logs with Guild ID context."""
    def process(self, msg, kwargs):
        guild_id = kwargs.pop('guild_id', self.extra.get('guild_id'))
        prefix = f"[Guild: {guild_id}]" if guild_id else "[Global]"
        return f"{prefix} {msg}", kwargs

def setup_logger(name="EventBot", log_file="logs/discord_event_bot.log", level=logging.INFO):
    # Ensure the logs directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Standard format with fixed-width level names for better alignment
    formatter = logging.Formatter('%(asctime)s - %(levelname)-8s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Rotating file handler: 20MB max, keep 5 backups (120MB total)
    handler = RotatingFileHandler(log_file, maxBytes=20*1024*1024, backupCount=5, encoding='utf-8')
    handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    base_logger = logging.getLogger(name)
    base_logger.setLevel(level)
    
    # Clear existing handlers if already setup
    if base_logger.handlers:
        base_logger.handlers.clear()
        
    base_logger.addHandler(handler)
    base_logger.addHandler(console_handler)

    # Wrap in our contextual adapter
    return GuildLoggerAdapter(base_logger, {"guild_id": None})

# Create the main logger that the rest of the bot will use
log = setup_logger()

def set_log_level(level_name):
    """Update the global logger level by name (INFO, DEBUG, ERROR)."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    log.logger.setLevel(level)
    for handler in log.logger.handlers:
        handler.setLevel(level)
    log.info(f"Logging level set to {level_name.upper()}")
