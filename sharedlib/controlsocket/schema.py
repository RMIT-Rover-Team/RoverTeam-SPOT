# sharedlib/controlsocket/schema.py
from .input import InputRegistry

def register_axis(registry: InputRegistry, name: str, callback=None):
    registry.register_input(name, type_="axis", callback=callback)

def register_bool(registry: InputRegistry, name: str, callback=None):
    registry.register_input(name, type_="bool", callback=callback)

def register_enum(registry: InputRegistry, name: str, values, callback=None):
    registry.register_input(name, type_="enum", values=values, callback=callback)