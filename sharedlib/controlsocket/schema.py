# sharedlib/controlsocket/schema.py
from .input import InputRegistry

def register_axis(registry: InputRegistry, name: str, min_val=-1.0, max_val=1.0, deadzone=0.0, callback=None):
    registry.register_input(name, type_="axis", min_val=min_val, max_val=max_val, deadzone=deadzone, callback=callback)

def register_bool(registry: InputRegistry, name: str, callback=None):
    registry.register_input(name, type_="bool", callback=callback)

def register_enum(registry: InputRegistry, name: str, values, callback=None):
    registry.register_input(name, type_="enum", values=values, callback=callback)