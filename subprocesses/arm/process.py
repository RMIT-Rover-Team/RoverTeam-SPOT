import asyncio
import argparse
import json
import logging
import signal

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema
from sharedlib.canbus.client import CANClient
from sharedlib.actuator.actuator_manager import ActuatorManager
from sharedlib.actuator.odrive import ODriveActuator


# -------------------------
# LOGGING
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {"level": record.levelname, "msg": record.getMessage()}
        print(json.dumps(log_obj), flush=True)


logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(JsonHandler())


# -------------------------
# ODRIVE CONFIG
# -------------------------
ACTUATOR_NAME = "drive_axis"
ODRIVE_NODE_ID = 0x4   # change to match your ODrive node ID

actuator = ODriveActuator(
    name=ACTUATOR_NAME,
    node_id=ODRIVE_NODE_ID
)

manager: ActuatorManager | None = None

# Velocity command (deg/sec from input)
commanded_velocity_deg = 0.0

# Shutdown flag
shutdown_event = asyncio.Event()


# -------------------------
# INPUT CALLBACK
# -------------------------
async def handle_pitch_input(value: float):
    global commanded_velocity_deg
    commanded_velocity_deg = value


# -------------------------
# CONTROL LOOP
# -------------------------
async def control_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():

        # Convert deg/sec -> turns/sec (ODrive native)
        turns_per_sec = commanded_velocity_deg / 360.0

        actuator.set_velocity(turns_per_sec)

        await control_socket.outputs.update_output(
            "pitch_velocity_cmd",
            commanded_velocity_deg,
        )

        await asyncio.sleep(interval)


# -------------------------
# HEARTBEAT LOOP
# -------------------------
async def heartbeat_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():

        await control_socket.outputs.update_output(
            "heartbeat",
            True,
        )

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
    global manager

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # -------------------------
    # CAN setup
    # -------------------------
    can_client = CANClient()
    await can_client.start()

    manager = ActuatorManager(can_client, rate_hz=50.0)
    manager.register(actuator)
    asyncio.create_task(manager.loop())

    # Arm ODrive
    actuator.request_arm()

    # -------------------------
    # WebSocket setup
    # -------------------------
    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    # Register pitch input (deg/sec)
    schema.register_axis(
        control_socket.inputs,
        "pitch",
        callback=lambda v: asyncio.create_task(handle_pitch_input(v)),
    )

    # Outputs
    control_socket.outputs.register_output("pitch_velocity_cmd")
    control_socket.outputs.register_output("heartbeat")

    await control_socket.start()

    logger.info(
        f"ODrive velocity control running on ws://{ws_host}:{ws_port}"
    )

    control_task = asyncio.create_task(
        control_loop(control_socket, status_interval)
    )

    heartbeat_task = asyncio.create_task(
        heartbeat_loop(control_socket, heartbeat_interval)
    )

    # Wait for shutdown
    await shutdown_event.wait()

    # -------------------------
    # Safe stop
    # -------------------------
    actuator.set_velocity(0.0)
    actuator.request_disarm()

    control_task.cancel()
    heartbeat_task.cancel()

    await asyncio.sleep(0)

    await control_socket.stop()
    await can_client.close()

    logger.info("Shutdown complete")


# -------------------------
# ENTRYPOINT
# -------------------------
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