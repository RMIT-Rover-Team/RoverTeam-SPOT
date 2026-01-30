import sys

from .scan_windows import scan_windows
from .scan_linux import scan_linux

def scan(ignore_list, logger):
    if sys.platform.startswith("win"):
        return scan_windows(ignore_list, logger)
    elif sys.platform.startswith("linux"):
        return scan_linux(ignore_list, logger)
    else:
        logger.error(f"Unsupported platform: {sys.platform}")
        return []
