import asyncio
import argparse
import json
import logging
import websockets

from canbus.can_wrapper import WrappedCanbus
from telemetry_ws.server import CanTelemetryServer
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

        except zmq.Again:
            await asyncio.sleep(0.01)  # prevent CPU spin


async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# Extra Tasks
# -------------------------


async def canbus_telemetry_loop(can_port, ws_port):
    bus = WrappedCanbus(can_port)
    telemetry_server = CanTelemetryServer()

    async with websockets.serve(telemetry_server.handle_connection, "0.0.0.0", ws_port):
        logger.info(f"CAN Polling active: {can_port} -> WS:{ws_port}")

        while True:
            frame = bus.read_msg()

            if frame:
                asyncio.create_task(telemetry_server.broadcast(frame))
            else:
                await asyncio.sleep(0.001)


# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str):
    # Setup ZMQ
    ctx = zmq.asyncio.Context()
    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # Required tasks
    receive_task = asyncio.create_task(receive_loop(sub_socket))
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))

    # Extra tasks
    telemetry_task = asyncio.create_task(
        canbus_telemetry_loop(args.can_port, args.ws_port)
    )
    try:
        await asyncio.gather(
            # Required tasks
            receive_task,
            heartbeat_task,
            # Extra tasks
            telemetry_task,
        )
    except asyncio.CancelledError:
        logging.info("Shutdown received, cancelling tasks")
    finally:
        # Required tasks
        receive_task.cancel()
        heartbeat_task.cancel()

        # Extra tasks
        telemetry_task.cancel()

        # propagate cancellation
        await asyncio.sleep(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--heartbeat", type=float, default=1.0, help="Heartbeat interval in seconds"
    )
    parser.add_argument(
        "--sub_url", type=str, default="tcp://127.0.0.1:5555", help="ZMQ SUB socket URL"
    )
    parser.add_argument("--can_port", type=str, default="vcan0")
    parser.add_argument("--ws_port", type=int, default=8766)
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.sub_url))
