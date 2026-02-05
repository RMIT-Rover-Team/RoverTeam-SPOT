import logging
from aiohttp import web, WSMsgType
from .cors import cors_middleware
from .receiver import handle_message
from .startup import send_startup_message

# -------------------------
# MODULE-LEVEL STATE
# -------------------------
clients: set[web.WebSocketResponse] = set()

# -------------------------
# HELPERS
# -------------------------
def get_client_count() -> int:
    return len(clients)

async def broadcast(message: str):
    dead = []

    for ws in clients:
        if ws.closed:
            dead.append(ws)
            continue

        try:
            await ws.send_str(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)

# -------------------------
# WEBSOCKET HANDLER
# -------------------------
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    clients.add(ws)
    logging.info("WebSocket client connected")

    # Send startup banner
    await send_startup_message(ws.send_str)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await handle_message(msg.data, broadcast)

            elif msg.type == WSMsgType.ERROR:
                logging.warning(
                    f"WebSocket error: {ws.exception()}"
                )

    finally:
        clients.discard(ws)
        logging.info("WebSocket client disconnected")

    return ws

# -------------------------
# SERVER STARTUP
# -------------------------
async def start_telemetry_server(
    host="0.0.0.0",
    port=3002,
):
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/ws", websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)

    logging.warning(
        f"Telemetry WebSocket server listening on ws://{host}:{port}/ws"
    )

    await site.start()