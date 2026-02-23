# sharedlib/controlsocket/controlsocket.py
from typing import Dict, Any
from sharedlib.websocket.server import WebSocketServer
from .input import InputRegistry
from .output import OutputRegistry


class ControlSocket:
    def __init__(self, host: str, port: int, name: str, *, allow_multiple_clients: bool = False):
        self._server = WebSocketServer(
            host,
            port,
            name,
            allow_multiple_clients=allow_multiple_clients,
        )

        self.name = name
        self.inputs = InputRegistry()
        self.outputs = OutputRegistry(self._server)

        # Attach internal listener for incoming WS messages
        self._server.add_listener(self._handle_message)

    async def start(self):
        await self._server.start()

    async def stop(self):
        await self._server.stop()

    async def _handle_message(self, data: Dict[str, Any], client, server):
        if "inputs" not in data:
            return

        for key, value in data["inputs"].items():
            await self.inputs.handle_input(key, value)