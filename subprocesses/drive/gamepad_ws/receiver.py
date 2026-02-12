import json
from typing import Callable, Any

class Receiver:
    def __init__(self, callback):
        self.callback = callback
        self.control_active = False  # starts inactive

    async def receive(self, msg: str):
        data = json.loads(msg)
        
        if data.get("type") == "control_active":
            self.control_active = data.get("active", False)
        else:
            await self.callback(data)