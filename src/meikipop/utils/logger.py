# meikipop/utils/logger.py
import logging
from meikipop.config.config import APP_NAME
from meikipop.utils.console import console_manager

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

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # logging.INFO or TRACE_LEVEL_NUM

    if logger.hasHandlers():
        logger.handlers.clear()
    # logs go to stdout (if any) and to a buffer that is replayed when the console is opened from the tray menu
    console_manager.install_logging(logger, log_formatter)