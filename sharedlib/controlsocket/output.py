# sharedlib/controlsocket/output.py
import logging
from typing import Any, Dict
from sharedlib.websocket.server import WebSocketServer

log = logging.getLogger(__name__)


class OutputRegistry:
    def __init__(self, server: WebSocketServer):
        self._outputs: Dict[str, Dict[str, Any]] = {}
        self._state: Dict[str, Any] = {}
        self._server = server

    def register_output(
        self,
        name: str,
        type_: str = "float",
        *,
        min_val: float = None,
        max_val: float = None,
    ):
        self._outputs[name] = {"type": type_, "min": min_val, "max": max_val}

    async def update_output(self, name: str, value: Any):
        if name not in self._outputs:
            log.warning("Unknown output: %s", name)
            return

        self._state[name] = value
        await self._server.broadcast({"outputs": {name: value}})

    @property
    def state(self):
        return dict(self._state)