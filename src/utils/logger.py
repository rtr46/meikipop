# src/utils/logger.py
import logging
import sys

from src.config.config import APP_NAME


def setup_logging():
    log_formatter = logging.Formatter(
        f"%(asctime)s - [%(levelname)-7s] - [{APP_NAME}] - %(message)s",
        datefmt='%H:%M:%S'
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(log_formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)