import asyncio
import argparse
import json
import logging

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel

import zmq
import zmq.asyncio

# -------------------------
# CONFIG
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {"level": record.levelname, "msg": record.getMessage()}
        print(json.dumps(log_obj), flush=True)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(JsonHandler())

# -------------------------
# ZMQ TELEMETRY
# -------------------------
def send_startup_message(ch):
    ch.send("CLEARSCREEN")
    ch.send("INFO Starting...")
    ch.send("WARNING \n   _______  ____  ______")
    ch.send("WARNING   / __/ _ \\/ __ \\/_  __/")
    ch.send("WARNING  _\\ \\/ ___/ /_/ / / /")
    ch.send("WARNING /___/_/   \\____/ /_/")  
    ch.send("WARNING SOFTWARE PLATFORM for")
    ch.send("WARNING ONBOARD TELEMETRY")
    ch.send("INFO \nDesigned for the:")
    ch.send("WARNING \n⣏⡉ ⡎⢱ ⡇⢸ ⡇ ⡷⣸ ⡎⢱ ⢇⡸")
    ch.send("WARNING ⠧⠤ ⠣⠪ ⠣⠜ ⠇ ⠇⠹ ⠣⠜ ⠇⠸")
    ch.send("WARNING SOFTWARE STACK\n\n")
            

async def receive_loop(sub_socket):
    """Continuously receive ZMQ messages."""
    while True:
        try:
            msg = await sub_socket.recv_string(flags=zmq.NOBLOCK)

            if msg.startswith("TELEMETRY "):
                for ch in list(channels):
                    if ch.readyState == "open":
                        ch.send(msg[len("TELEMETRY "):])
        except zmq.Again:
            await asyncio.sleep(0.01)  # prevent CPU spin

async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)

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
# WEBRTC LOGGING SERVER
# -------------------------
pcs: set[RTCPeerConnection] = set()
channels: set[RTCDataChannel] = set()

async def handle_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        logging.info(f"Incoming WebRTC channel")
        channels.add(channel)

        send_startup_message(channel)

        @channel.on("close")
        def on_close():
            channels.discard(channel)

        @channel.on("message")
        def on_message(message):
            logging.info(f"Received from peer: {message}")

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

async def start_webrtc_server(host="0.0.0.0", port=3002):
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_post("/offer", handle_offer)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    logging.warning(f"WebRTC logging server listening on {host}:{port}")
    await site.start()

# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str, webrtc_host: str, webrtc_port: int):
    # Setup ZMQ
    ctx = zmq.asyncio.Context()
    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # Start async tasks
    receive_task = asyncio.create_task(receive_loop(sub_socket))
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))
    webrtc_task = asyncio.create_task(start_webrtc_server(webrtc_host, webrtc_port))

    try:
        await asyncio.gather(receive_task, heartbeat_task, webrtc_task)
    except asyncio.CancelledError:
        logging.info("Shutdown received, cancelling tasks")
        for ch in list(channels):
            if ch.readyState == "open":
                ch.send("ERROR [supervisor]: Received shutdown signal")
    finally:
        receive_task.cancel()
        heartbeat_task.cancel()
        webrtc_task.cancel()
        await asyncio.sleep(0)  # propagate cancellation

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=float, default=1.0, help="Heartbeat interval in seconds")
    parser.add_argument("--sub_url", type=str, default="tcp://127.0.0.1:5555", help="ZMQ SUB socket URL")
    parser.add_argument("--webrtc_host", type=str, default="0.0.0.0", help="WebRTC server host")
    parser.add_argument("--webrtc_port", type=int, default=3002, help="WebRTC server port")
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.sub_url, args.webrtc_host, args.webrtc_port))