import json
from typing import Callable, Any

class Receiver:
    def __init__(self, callback):
        self.callback = callback
        self.control_active = False  # starts inactive

    async def receive(self, msg: str):
        data = json.loads(msg)
        
        if "control_active" in data:
            self.control_active = data["control_active"]
        
        await self.callback(data)