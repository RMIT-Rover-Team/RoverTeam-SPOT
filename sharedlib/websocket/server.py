import asyncio
import json
import logging
from typing import Callable, Awaitable, Set, Optional

from aiohttp import web, WSMsgType
from .cors import cors_middleware as default_cors_middleware

log = logging.getLogger(__name__)


MessageListener = Callable[[dict, web.WebSocketResponse, "WebSocketServer"], Awaitable[None]]


class WebSocketServer:
    def __init__(
        self,
        host: str,
        port: int,
        name: str,
        *,
        allow_multiple_clients: bool = True,
        cors_middleware: Optional[list] = None,
    ):
        self._host = host
        self._port = port
        self.name = name
        self._allow_multiple = allow_multiple_clients

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

        self._clients: Set[web.WebSocketResponse] = set()
        self._listeners: Set[MessageListener] = set()

        self._middlewares = (
            cors_middleware if cors_middleware is not None else [default_cors_middleware]
        )

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def add_listener(self, listener: MessageListener):
        self._listeners.add(listener)

    def remove_listener(self, listener: MessageListener):
        self._listeners.discard(listener)

    def get_client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, data):
        message = self._serialize(data)

        dead = []
        for ws in self._clients:
            if ws.closed:
                dead.append(ws)
                continue
            try:
                await ws.send_str(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._clients.discard(ws)

    async def send(self, data, client: web.WebSocketResponse):
        if client in self._clients and not client.closed:
            await client.send_str(self._serialize(data))

    # ---------------------------------------------------------
    # Internal
    # ---------------------------------------------------------

    def _serialize(self, data) -> str:
        if isinstance(data, str):
            return data
        return json.dumps(data)

    async def _websocket_handler(self, request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Single-client mode enforcement
        if not self._allow_multiple and self._clients:
            log.warning("Rejecting new WS client (single-client mode)")
            await ws.send_str(json.dumps({"error": "already_connected"}))
            await ws.close()
            return ws

        self._clients.add(ws)
        log.info("WS client connected: %s", request.remote)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except Exception:
                        log.warning("Invalid JSON received")
                        continue

                    # Notify all listeners
                    for listener in list(self._listeners):
                        try:
                            await listener(data, ws, self)
                        except Exception as e:
                            log.exception("Listener error: %s", e)

                elif msg.type == WSMsgType.ERROR:
                    log.warning("WS error: %s", ws.exception())

        finally:
            self._clients.discard(ws)
            log.info("WS client disconnected: %s", request.remote)

        return ws
    
    async def _ping_handler(self, request: web.Request):
        """Respond with the subprocess name."""
        return web.Response(text=self.name)

    # ---------------------------------------------------------
    # Start / Stop
    # ---------------------------------------------------------

    async def start(self):
        self._app = web.Application(middlewares=self._middlewares)
        self._app.router.add_get("/ws", self._websocket_handler)
        self._app.router.add_get("/ping", self._ping_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        log.info("WebSocket server running on %s:%d", self._host, self._port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._app = None
            self._clients.clear()
            log.info("WebSocket server stopped")