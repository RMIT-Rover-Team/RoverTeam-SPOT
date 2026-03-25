import asyncio
from typing import Dict, Any, Callable, List
from sharedlib.websocket.server import WebSocketServer
from .input import InputRegistry
from .output import OutputRegistry

class ControlSocket:
    def __init__(
        self, host: str, port: int, name: str, *, allow_multiple_clients: bool = False
    ):
        self._server = WebSocketServer(
            host,
            port,
            name,
            allow_multiple_clients=allow_multiple_clients,
        )

        self.name = name
        self.inputs = InputRegistry()
        self.outputs = OutputRegistry(self._server)

        self._server.add_listener(self._handle_message)

        # New: connection callbacks
        self._on_connect_callbacks: List[Callable[[], None]] = []
        self._connected = False

    def on_connect(self, callback: Callable[[], None]):
        """Register a callback to fire once when the first client connects."""
        self._on_connect_callbacks.append(callback)

    async def start(self):
        await self._server.start()
        # Poll for first client after server start
        if not self._connected:
            while len(self._server._clients) == 0:  # or whatever property tracks connected clients
                await asyncio.sleep(0.05)
            self._connected = True
            for cb in self._on_connect_callbacks:
                cb()  # fire once

    async def stop(self):
        await self._server.stop()

    async def _handle_message(self, data: Dict[str, Any], client, server):
        if "inputs" not in data:
            return

        for key, value in data["inputs"].items():
            await self.inputs.handle_input(key, value)
