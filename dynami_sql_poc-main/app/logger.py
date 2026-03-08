import logging
from logging.handlers import RotatingFileHandler
import json_logging
from app.logs_fields_config import init_json_logger


def init_logger(app) -> None:
    init_json_logger()
    json_logging.init_fastapi(enable_json=True)
    json_logging.init_request_instrument(app, exclude_url_patterns=[".*/docs", ".*/openapi.json", ".*/favicon.ico"])

    log_file_path = f'logs/{app.title}.log'
    access_log_file_path = 'logs/access.log'

    rotate_file_handler = RotatingFileHandler(log_file_path, maxBytes=268000000, backupCount=1)
    access_rotate_file_handler = RotatingFileHandler(access_log_file_path, maxBytes=268000000, backupCount=1)
    access_rotate_file_handler.setFormatter(json_logging.JSONRequestLogFormatter())

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(rotate_file_handler)

    access_logger = json_logging.get_request_logger()
    access_logger.addHandler(access_rotate_file_handler)