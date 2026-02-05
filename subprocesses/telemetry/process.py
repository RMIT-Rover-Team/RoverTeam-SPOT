import asyncio
import argparse
import json
import logging

import zmq
import zmq.asyncio

from telemetry_ws.server import (
    start_telemetry_server,
    broadcast,
)

from vitals.core import collect_vitals

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

filter_list = []

# -------------------------
# ZMQ TELEMETRY
# -------------------------
async def receive_loop(sub_socket):
    """Continuously receive ZMQ messages."""
    while True:
        try:
            msg = await sub_socket.recv_string(flags=zmq.NOBLOCK)

            if msg.startswith("TELEMETRY "):
                if not any(ext in msg for ext in filter_list):
                    await broadcast(msg[len("TELEMETRY "):])
        except zmq.Again:
            await asyncio.sleep(0.01)  # prevent CPU spin

async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)

# -------------------------
# VITALS
# -------------------------
async def vitals_loop(interval: float):
    while True:
        vitals = collect_vitals()
        msg = json.dumps({"type": "vitals", "data":vitals})
        await broadcast(f"JSON {msg}")
        await asyncio.sleep(interval)

# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str, webrtc_host: str, webrtc_port: int, vitals_interval: float):
    # Setup ZMQ
    ctx = zmq.asyncio.Context()
    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # Start async tasks
    receive_task = asyncio.create_task(receive_loop(sub_socket))
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))
    webrtc_task = asyncio.create_task(start_telemetry_server(webrtc_host, webrtc_port))
    vitals_task = asyncio.create_task(vitals_loop(vitals_interval))

    try:
        await asyncio.gather(receive_task, heartbeat_task, webrtc_task)
    except asyncio.CancelledError:
        logging.info("Shutdown received, cancelling tasks")
        await broadcast("ERROR [telemetry]: Telemetry shutting down, disconnecting...")
    finally:
        receive_task.cancel()
        heartbeat_task.cancel()
        webrtc_task.cancel()
        vitals_task.cancel()
        await asyncio.sleep(0)  # propagate cancellation

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=float, default=1.0, help="Heartbeat interval in seconds")
    parser.add_argument("--sub_url", type=str, default="tcp://127.0.0.1:5555", help="ZMQ SUB socket URL")
    parser.add_argument("--ws_host", type=str, default="0.0.0.0", help="Web Socket server host")
    parser.add_argument("--ws_port", type=int, default=3002, help="Web Socket server port")
    parser.add_argument("--vitals_interval", type=float, default=10, help="Vitals interval in seconds")
    parser.add_argument("--ignore_filter", default=[], action="append", help="Filter out logs containing these strings")
    args = parser.parse_args()
    filter_list = args.ignore_filter

    asyncio.run(main(args.heartbeat, args.sub_url, args.ws_host, args.ws_port, args.vitals_interval))