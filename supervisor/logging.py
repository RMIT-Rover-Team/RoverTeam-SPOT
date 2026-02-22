# supervisor/logging.py

import logging
from typing import Optional


# ============================================================
# ANSI COLOUR FORMATTER
# ============================================================
class AnsiFormatter(logging.Formatter):
    """
    Simple ANSI colour formatter for console output.
    """

    COLORS = {
        "DEBUG": "\033[90m",        # Grey
        "INFO": "\033[0m",          # Default
        "WARNING": "\033[93m",      # Yellow
        "ERROR": "\033[31m",        # Red
        "CRITICAL": "\033[91;1m",   # Bright Red + Bold
        "SUCCESS": "\033[92m",      # Green (custom level support)
    }

    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


# ============================================================
# LOGGER FACTORY
# ============================================================
def get_logger(
    name: str = "supervisor",
    debug: bool = False,
) -> logging.Logger:
    """
    Create (or return existing) configured logger.

    Safe to call multiple times.
    """

    logger = logging.getLogger(name)

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler()
    formatter = AnsiFormatter("%(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False  # Prevent double printing

    return logger


# ============================================================
# SUCCESS LOG LEVEL (CUSTOM)
# ============================================================
SUCCESS_LEVEL = 25  # Between INFO (20) and WARNING (30)

def _add_success_level():
    if not hasattr(logging, "SUCCESS"):
        logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

        def success(self, message, *args, **kwargs):
            if self.isEnabledFor(SUCCESS_LEVEL):
                self._log(SUCCESS_LEVEL, message, args, **kwargs)

        logging.Logger.success = success


_add_success_level()