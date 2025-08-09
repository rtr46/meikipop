# src/utils/logger.py
import logging
import sys

from src.config.config import APP_NAME

TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)


logging.Logger.trace = trace

def setup_logging():
    log_formatter = logging.Formatter(
        f"%(asctime)s - [%(levelname)-5s] - [{APP_NAME}] - %(message)s",
        datefmt='%H:%M:%S'
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(log_formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # logging.INFO or TRACE_LEVEL_NUM

    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)