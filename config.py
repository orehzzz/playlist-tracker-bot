import logging
import configparser
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config_file_path = os.path.join(os.path.dirname(__file__), '.', 'config.ini')

config = configparser.ConfigParser()

if not config.read(config_file_path):
    logger.error(f"Configuration file {config_file_path} not found.")
    raise FileNotFoundError(f"Configuration file {config_file_path} not found.")

try:
    SPOTIFY_CLIENT_ID = config["Spotify"]["client_id"]
    SPOTIFY_CLIENT_SECRET = config["Spotify"]["client_secret"]
    BOT_TOKEN = config["Telegram"]["bot_token"]
    CREATOR_ID = config["Telegram"]["creator_id"]
    DB_NAME = config["Database"]["name"]
    DB_USER = config["Database"]["user"]
    DB_PASSWORD = config["Database"]["password"]
except KeyError as e:
    logger.error(f"Missing key in configuration file: {e}")
    raise
except ValueError as e:
    logger.error(f"Invalid value in configuration file: {e}")
    raise