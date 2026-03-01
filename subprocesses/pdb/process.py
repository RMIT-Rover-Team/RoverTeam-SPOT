import argparse
import asyncio
import json
import logging
import signal

from sharedlib.websocket.server import WebSocketServer
from sharedlib.canbus.client import CANClient
from telemetry.telemetry import PDBTelemetryManager


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

shutdown_event = asyncio.Event()

pdb_telemetry_ids = {
    "SWITCH": 0xA,
    "BUCK1": 0x06,
    "BUCK2": 0x07,
    "BMS": 0x08,
}


async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# Extra Tasks
# -------------------------


async def some_task():
    while True:
        # Intervalled code here
        await asyncio.sleep(10)


# -------------------------
# CLEAN SHUTDOWN
# -------------------------
def request_shutdown():
    logger.info("Shutdown signal received")
    shutdown_event.set()


# -------------------------
# MAIN
# -------------------------
async def main(
    ws_host: str,
    ws_port: int,
    ws_name: str,
    status_interval: float,
    heartbeat_interval: float,
):
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # -------------------------
    # CAN setup
    # -------------------------
    can_client = CANClient()
    try:
        await can_client.start()
    except Exception as e:
        logger.warning(e)
    # BUCK 1: 6
    # BUCK 2: 7
    # SWITCH: 10
    PDBTelemetryManager.register_all()
    # asyncio.create_task()

    # Required tasks
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))

    # Extra tasks
    webrtc_task = asyncio.create_task(some_task())

    try:
        await asyncio.gather(
            # Required tasks
            heartbeat_task,
            # Extra tasks
            webrtc_task,
        )
    except asyncio.CancelledError:
        logging.info("Shutdown received, cancelling tasks")
    finally:
        # Required tasks
        heartbeat_task.cancel()

        # Extra tasks
        webrtc_task.cancel()

        # propagate cancellation
        await asyncio.sleep(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=8766)
    parser.add_argument("--ws_name", type=str, default="odrive_velocity")
    parser.add_argument("--status_interval", type=float, default=0.02)
    parser.add_argument("--heartbeat", type=float, default=5.0)

    args = parser.parse_args()

    asyncio.run(
        main(
            args.ws_host,
            args.ws_port,
            args.ws_name,
            args.status_interval,
            args.heartbeat,
        )
    )
