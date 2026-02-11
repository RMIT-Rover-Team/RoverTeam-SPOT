import logging
from typing import Optional, Set

from aiohttp import web, WSMsgType
from .receiver import Receiver
from .cors import cors_middleware as default_cors_middleware

log = logging.getLogger(__name__)


class GamepadServer:
    """
    Serves:
      - WebSocket on /ws  → forwards text messages to Receiver
      - HTTP GET on /ping → returns plain service name
    All on the same host/port.
    """

    def __init__(
        self,
        host: str,
        port: int,
        receiver: Receiver,
        service_name: str = "drive",
        *,
        cors_middleware: Optional[list] = None,  # optional middleware list
    ):
        self._host = host
        self._port = port
        self._receiver = receiver
        self._service_name = service_name

        # aiohttp app + runner
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

        # track connected clients, if needed
        self._clients: Set[web.WebSocketResponse] = set()

        # optional list of middlewares, e.g. cors
        self._middlewares = cors_middleware if cors_middleware is not None else [default_cors_middleware]

    # ---------------------------------------------------------
    # Handlers
    # ---------------------------------------------------------
    async def _websocket_handler(self, request: web.Request):
        """
        Handles WS upgrade on /ws.
        Receives text messages and forwards them to the Receiver.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._clients.add(ws)
        log.info("Gamepad WS client connected: %s", request.remote)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # Forward to your Receiver instance.
                    await self._receiver.receive(msg.data)

                elif msg.type == WSMsgType.ERROR:
                    log.warning("Gamepad WS error: %s", ws.exception())

        finally:
            self._clients.discard(ws)
            log.info("Gamepad WS client disconnected: %s", request.remote)

        return ws

    async def _handle_ping(self, request: web.Request):
        try:
            return web.Response(text=self._service_name)
        except Exception as e:
            print("Error in /ping handler")
            return web.Response(status=500, text=str(e))

    # ---------------------------------------------------------
    # Start / Stop
    # ---------------------------------------------------------
    async def start(self):
        """
        Build the aiohttp app, register routes, and start listening.
        """
        # Build app with optional middleware
        self._app = web.Application(middlewares=self._middlewares)

        # Store receiver or any shared state on app if needed
        # Optionally: self._app["receiver"] = self._receiver

        # Routes
        self._app.router.add_get("/ws", self._websocket_handler)
        self._app.router.add_get("/ping", self._handle_ping)

        # Runner + site
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        log.info(
            "Gamepad server listening on http://%s:%d (WS at /ws, ping at /ping)",
            self._host,
            self._port,
        )

    async def stop(self):
        """
        Cleanly stop the aiohttp server.
        """
        if self._runner:
            await self._runner.cleanup()
            log.info("Gamepad server stopped")
            self._runner = None
            self._app = None
            # Clear any clients if desired
            self._clients.clear()

    # ---------------------------------------------------------
    # Utility: broadcast if needed
    # ---------------------------------------------------------
    async def broadcast(self, message: str):
        """
        Send a text message to all connected WS clients.
        """
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

    def get_client_count(self) -> int:
        return len(self._clients)