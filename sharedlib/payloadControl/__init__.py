# __init__.py

try:
    # Try to import the native extension module
    from . import pyRover as pyRover
except (ImportError, OSError):
    # Fall back to emulator if native import fails
    from . import fallbackPayloadEmulator as pyRover
