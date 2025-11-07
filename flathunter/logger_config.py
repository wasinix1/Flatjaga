"""Provides logger with color support"""
import logging
import os
from pprint import pformat


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for prettier logging"""
    if os.name == 'posix':
        RESET = '\033[0m'
        BOLD = '\033[1m'
        DIM = '\033[2m'

        # Text colors
        BLACK = '\033[30m'
        RED = '\033[31m'
        GREEN = '\033[32m'
        YELLOW = '\033[33m'
        BLUE = '\033[34m'
        MAGENTA = '\033[35m'
        CYAN = '\033[36m'
        WHITE = '\033[37m'

        # Bright colors
        BRIGHT_RED = '\033[91m'
        BRIGHT_GREEN = '\033[92m'
        BRIGHT_YELLOW = '\033[93m'
        BRIGHT_BLUE = '\033[94m'
        BRIGHT_MAGENTA = '\033[95m'
        BRIGHT_CYAN = '\033[96m'
    else:
        # No colors on Windows (unless ANSI support is enabled)
        RESET = BOLD = DIM = ''
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ''
        BRIGHT_RED = BRIGHT_GREEN = BRIGHT_YELLOW = BRIGHT_BLUE = BRIGHT_MAGENTA = BRIGHT_CYAN = ''


class LoggerHandler(logging.StreamHandler):
    """Formats logs and alters WebDriverManager's logs properties"""

    _CYELLOW = Colors.BRIGHT_YELLOW
    _CBLUE = Colors.BRIGHT_BLUE
    _COFF = Colors.RESET
    _FORMAT = '[' + _CBLUE + '%(asctime)s' + _COFF + \
              '|' + _CBLUE + '%(filename)-24s' + _COFF + \
              '|' + _CYELLOW + '%(levelname)-8s' + _COFF + \
              ']: %(message)s'
    _DATE_FORMAT = '%Y/%m/%d %H:%M:%S'

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(
            fmt=self._FORMAT,
            datefmt=self._DATE_FORMAT
        ))

    def emit(self, record):
        # Log record came from webdriver-manager logger
        if record.name == "WDM":
            # Filename to display in log
            record.filename = "<WebDriverManager>"
            # Always display loglevel as DEBUG
            record.levelname = "DEBUG"
        super().emit(record)


def setup_wdm_logger(wdm_new_logger_handler):
    """Setup "webdriver-manager" module's logger"""
    wdm_log = logging.getLogger('WDM')
    # Only allow critical-level logs by default (mute)
    wdm_log.setLevel(logging.CRITICAL)
    wdm_log.propagate = False
    # wdm_log.removeHandler(wdm_logger_handler)
    wdm_log.addHandler(wdm_new_logger_handler)
    return wdm_log


# Setup Flathunter logger
logger_handler = LoggerHandler()
logging.basicConfig(level=logging.INFO, handlers=[logger_handler])
logger = logging.getLogger('flathunt')

# Setup "webdriver-manager" module's logger
wdm_logger = setup_wdm_logger(logger_handler)

# Setup "requests" module's logger
logging.getLogger("requests").setLevel(logging.WARNING)

def configure_logging(config):
    """Setup the logging classes based on verbose config flag"""
    if config.verbose_logging():
        logger.setLevel(logging.DEBUG)
        # Allow logging of "webdriver-manager" module on verbose mode
        wdm_logger.setLevel(logging.INFO)
    logger.debug("Settings from config: %s", pformat(config))
