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
async def receive_loop(sub_socket):
    """Continuously receive ZMQ messages."""
    while True:
        try:
            msg = await sub_socket.recv_string(flags=zmq.NOBLOCK)
            if msg.startswith("TELEMETRY "):
                logging.info(f"ZMQ: {msg[len('TELEMETRY '):]}")
        except zmq.Again:
            await asyncio.sleep(0.01)  # prevent CPU spin

async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)

# -------------------------
# WEBRTC LOGGING SERVER
# -------------------------
pcs = set()

async def handle_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        logging.info(f"Incoming WebRTC channel: {channel.label}")

        @channel.on("message")
        def on_message(message):
            try:
                # Attempt to parse JSON; fallback to raw string
                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                        logging.info(f"WebRTC {channel.label} JSON: {data}")
                    except json.JSONDecodeError:
                        logging.info(f"WebRTC {channel.label}: {message}")
                else:
                    logging.info(f"WebRTC {channel.label} (binary) {len(message)} bytes")
            except Exception as e:
                logging.error(f"Error handling WebRTC message: {e}")

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

async def start_webrtc_server(host="0.0.0.0", port=3002):
    app = web.Application()
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