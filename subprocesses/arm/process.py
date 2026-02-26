import asyncio
import argparse
import json
import logging
import signal

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema
from sharedlib.canbus.client import CANClient
from sharedlib.actuator.actuator_manager import ActuatorManager
from sharedlib.actuator.myactuator import MyActuator


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
# ACTUATOR CONFIG
# -------------------------
ACTUATOR_NAME = "J1"
ACTUATOR_ID = 0x142

actuator = MyActuator(ACTUATOR_NAME, ACTUATOR_ID)
manager: ActuatorManager | None = None

# Current velocity command (deg/sec)
commanded_velocity = 0.0

# Shutdown flag
shutdown_event = asyncio.Event()


# -------------------------
# INPUT CALLBACK
# -------------------------
async def handle_pitch_input(value: float):
    """
    Pitch input is degrees per second.
    """
    global commanded_velocity
    commanded_velocity = value


# -------------------------
# CONTROL LOOP
# -------------------------
async def control_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():

        actuator.set_velocity(commanded_velocity)

        # Minimal telemetry
        await control_socket.outputs.update_output(
            "pitch_velocity_cmd",
            commanded_velocity,
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
):
    global manager

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # Start CAN
    can_client = CANClient()
    await can_client.start()

    manager = ActuatorManager(can_client, rate_hz=50.0)
    manager.register(actuator)
    asyncio.create_task(manager.loop())

    # Control socket
    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    # Register pitch axis only (deg/sec)
    schema.register_axis(
        control_socket.inputs,
        "pitch",
        callback=lambda v: asyncio.create_task(handle_pitch_input(v)),
    )

    # Minimal output
    control_socket.outputs.register_output("pitch_velocity_cmd")

    await control_socket.start()

    logger.info(
        f"Velocity control running on ws://{ws_host}:{ws_port}"
    )

    control_task = asyncio.create_task(
        control_loop(control_socket, status_interval)
    )

    # Wait for shutdown
    await shutdown_event.wait()

    # Stop motor safely
    actuator.set_velocity(0.0)

    control_task.cancel()
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
    parser.add_argument("--ws_name", type=str, default="single_velocity")
    parser.add_argument("--status_interval", type=float, default=0.02)

    args = parser.parse_args()

    asyncio.run(
        main(
            args.ws_host,
            args.ws_port,
            args.ws_name,
            args.status_interval,
        )
    )