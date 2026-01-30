import asyncio
import argparse
import json
import logging
import platform
import subprocess
import re
import signal

from scan_cameras.core import scan
from stream_cameras.core import stream_camera, cleanup_camera

import zmq
import zmq.asyncio

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame


# -------------------------
# LOGGING (JSON ONLY)
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        print(json.dumps(log_obj), flush=True)


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(JsonHandler())


# -------------------------
# CONFIG
# -------------------------
IS_WINDOWS = platform.system() == "Windows"

ZMQ_RECEIVE = False # No need to receive ZMQ commands in this process

pcs = set()
players = {}
ignore_list = []

# -------------------------
# ZMQ RECEIVE LOOP
# -------------------------
async def receive_loop(sub_socket):
    while ZMQ_RECEIVE:
        try:
            msg = await sub_socket.recv_string(flags=zmq.NOBLOCK)
            logger.warning(f"ZMQ RX: {msg}")
        except zmq.Again:
            await asyncio.sleep(0.01)


# -------------------------
# HEARTBEAT
# -------------------------
async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT", flush=True)
        await asyncio.sleep(interval)

# -------------------------
# HTTP HANDLERS
# -------------------------
async def handle_cameras(request):
    cameras = scan(ignore_list, logger)
    return web.json_response({"cameras":cameras})


async def handle_ping(request):
    return web.Response(text="pong")


async def handle_offer(request):
    params = await request.json()
    camera_id = int(params.get("camera_id", 0))

    cameras = scan(ignore_list, logger)
    camera = next((c for c in cameras if c["id"] == camera_id), None)
    if camera is None:
        return web.Response(status=404, text="Camera not found")

    logger.info(f"Opening camera: {camera["label"]}")

    pc = RTCPeerConnection()
    pcs.add(pc)

    try:
        track = await stream_camera(camera, logger)
        players[pc] = track
        pc.addTrack(track)
    except Exception as e:
        logger.error(f"Failed to open camera: {e}")
        return web.Response(status=500, text=str(e))

    @pc.on("connectionstatechange")
    async def on_state():
        if pc.connectionState in ("failed", "closed"):
            await cleanup_pc(pc)

    offer = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"],
    )

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    })

# -------------------------
# CORS
# -------------------------
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        return web.Response(
            status=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": request.headers.get(
                    "Access-Control-Request-Headers", "*"
                ),
            },
        )

    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# -------------------------
# CLEANUP
# -------------------------
async def cleanup_pc(pc):
    track = players.pop(pc, None)
    if track:
        try:
            await cleanup_camera(track, logger)
        except Exception as e:
            logger.warning(f"Failed to cleanup camera track: {e}")

    await pc.close()
    pcs.discard(pc)


async def on_shutdown(app):
    await asyncio.gather(*(cleanup_pc(pc) for pc in list(pcs)))


# -------------------------
# WEBRTC SERVER TASK
# -------------------------
async def webrtc_server_task(host: str, port: int):
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/cameras", handle_cameras)
    app.router.add_post("/offer", handle_offer)
    app.router.add_get("/ping", handle_ping)
    app.on_shutdown.append(on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.warning(f"WebRTC camera server listening on {host}:{port}")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("webrtc_server_task cancelled")
        await runner.cleanup()
        raise


# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str, host: str, port: int):
    ctx = zmq.asyncio.Context()
    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # WebRTC server
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/cameras", handle_cameras)
    app.router.add_post("/offer", handle_offer)
    app.router.add_get("/ping", handle_ping)
    app.on_shutdown.append(on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logger.warning(f"WebRTC camera server listening on {host}:{port}")

    # Tasks
    tasks = [
        asyncio.create_task(receive_loop(sub_socket)),
        asyncio.create_task(heartbeat_loop(heartbeat_interval)),
    ]

    # Shutdown event
    stop_event = asyncio.Event()

    def handle_stop(*args):
        stop_event.set()

    loop = asyncio.get_event_loop()
    if platform.system() == "Windows":
        signal.signal(signal.SIGINT, handle_stop)
        signal.signal(signal.SIGTERM, handle_stop)
    else:
        loop.add_signal_handler(signal.SIGINT, handle_stop)
        loop.add_signal_handler(signal.SIGTERM, handle_stop)

    # Wait for shutdown signal
    await stop_event.wait()

    # Cancel tasks
    for t in tasks:
        t.cancel()
    await asyncio.sleep(0)

    # Cleanup WebRTC server properly
    await site.stop()
    await runner.cleanup()
    logger.warning("WebRTC camera server shutdown complete")


# -------------------------
# ENTRYPOINT
# -------------------------
def handle_shutdown():
    for pc in list(pcs):
        asyncio.get_event_loop().create_task(cleanup_pc(pc))
    for task in asyncio.all_tasks():
        task.cancel()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=float, default=5.0)
    parser.add_argument("--sub_url", type=str, default="tcp://127.0.0.1:5555")
    parser.add_argument("--webrtc_host", type=str, default="0.0.0.0")
    parser.add_argument("--webrtc_port", type=int, default=3002)
    parser.add_argument("--ignore_cameras",action="append",default=[])
    args = parser.parse_args()
    ignore_list = args.ignore_cameras

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Cross-platform termination signals
    if platform.system() == "Windows":
        signal.signal(signal.SIGINT, lambda *_: handle_shutdown())
        signal.signal(signal.SIGTERM, lambda *_: handle_shutdown())
    else:
        loop.add_signal_handler(signal.SIGINT, handle_shutdown)
        loop.add_signal_handler(signal.SIGTERM, handle_shutdown)

    try:
        loop.run_until_complete(main(args.heartbeat, args.sub_url, args.webrtc_host, args.webrtc_port))
    except asyncio.CancelledError:
        logger.info("Cancelled")
    finally:
        loop.run_until_complete(on_shutdown(None))
        loop.close()