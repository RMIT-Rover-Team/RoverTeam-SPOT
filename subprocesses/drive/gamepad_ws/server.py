import logging
import websockets
from websockets.server import WebSocketServerProtocol

from .receiver import Receiver

log = logging.getLogger(__name__)


class GamepadWSServer:
    def __init__(
        self,
        host: str,
        port: int,
        receiver: Receiver,
    ):
        self._host = host
        self._port = port
        self._receiver = receiver
        self._server = None

    async def _client_loop(self, ws: WebSocketServerProtocol):
        log.info("Gamepad client connected: %s", ws.remote_address)

        try:
            async for message in ws:
                await self._receiver.receive(message)
        except websockets.ConnectionClosed:
            log.info("Gamepad client disconnected: %s", ws.remote_address)
        except Exception:
            log.exception("Gamepad websocket error")

    async def start(self):
        self._server = await websockets.serve(
            self._client_loop,
            self._host,
            self._port,
        )

        log.info("Gamepad WS listening on %s:%d", self._host, self._port)

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            log.info("Gamepad WS stopped")