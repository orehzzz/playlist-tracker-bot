import logging
from logging.handlers import RotatingFileHandler
import os


script_dir = os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(script_dir, ".", "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)


class ExcludeGetUpdatesFilter(logging.Filter):
    def filter(self, record):
        return "getUpdates" not in record.getMessage()


logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)

debug_handler = RotatingFileHandler(
    os.path.join(log_dir, "debug.log"), maxBytes=5 * 1024 * 1024, backupCount=3
)
debug_handler.setLevel(logging.DEBUG)
debug_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)

info_handler = RotatingFileHandler(
    os.path.join(log_dir, "info.log"), maxBytes=5 * 1024 * 1024, backupCount=3
)
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
info_handler.addFilter(ExcludeGetUpdatesFilter())

warning_handler = RotatingFileHandler(
    os.path.join(log_dir, "warning.log"), maxBytes=5 * 1024 * 1024, backupCount=3
)
warning_handler.setLevel(logging.WARNING)
warning_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)

error_handler = RotatingFileHandler(
    os.path.join(log_dir, "error.log"), maxBytes=5 * 1024 * 1024, backupCount=3
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)

logging.getLogger().addHandler(debug_handler)
logging.getLogger().addHandler(info_handler)
logging.getLogger().addHandler(warning_handler)
logging.getLogger().addHandler(error_handler)

#set logging level to info
logging.getLogger().setLevel(logging.INFO)