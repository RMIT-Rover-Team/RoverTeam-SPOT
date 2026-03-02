import argparse
import asyncio
import json
import logging
import signal

from subprocesses.pdb.telemetry.manager import PDBTelemetryManager

from sharedlib.canbus.client import CANClient
from sharedlib.controlsocket.controlsocket import ControlSocket


# -------------------------
# CONFIG
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {"level": record.levelname, "msg": record.getMessage()}
        print(json.dumps(log_obj), flush=True)


logger = logging.getLogger("pdb")
logger.setLevel(logging.INFO)
logger.addHandler(JsonHandler())

pdb_manager: PDBTelemetryManager | None = None
shutdown_event = asyncio.Event()

pdb_telemetry_ids = {
    "SWITCH": 0xA,
    "BUCK1": 0x06,
    "BUCK2": 0x07,
    "BMS": 0x08,
}


async def heartbeat_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# Extra Tasks
# -------------------------
async def pdb_telemetry_loop(
    pdb_manager: PDBTelemetryManager, control_socket: ControlSocket, interval: float
):
    while not shutdown_event.is_set():
        # 1. Get the data
        data = pdb_manager.get_snapshot()

        logger.info(data["buck1"][0])

        # 2. Send to Frontend via ControlSocket
        # This assumes you registered "pdb_data" in the main function
        await control_socket.outputs.update_output("pdb_data", data)

        # 3. Wait
        await asyncio.sleep(interval)


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
    await can_client.start()

    # BUCK 1: 6
    # BUCK 2: 7
    # SWITCH: 10
    pdb_manager = PDBTelemetryManager(can_client)
    pdb_manager.register_all()

    # -------------------------
    # Websocket
    # -------------------------
    control_socket = ControlSocket(ws_host, ws_port, ws_name)
    control_socket.outputs.register_output("pdb_data")
    control_socket.outputs.register_output("heartbeat")

    await control_socket.start()
    # Required tasks

    pdb_task = asyncio.create_task(
        pdb_telemetry_loop(pdb_manager, control_socket, interval=0.1)
    )
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(control_socket, heartbeat_interval)
    )

    # Wait for shutdown...
    await shutdown_event.wait()

    # Cleanup
    pdb_task.cancel()
    heartbeat_task.cancel()

    await asyncio.sleep(0)

    await control_socket.stop()
    await can_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=8766)
    parser.add_argument("--ws_name", type=str, default="pdb_telemetry")
    parser.add_argument("--status_interval", type=float, default=0.02)
    parser.add_argument("--heartbeat", type=float, default=2.0)

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
