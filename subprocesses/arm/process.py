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
from sharedlib.actuator.myactuator import MyActuator
from sharedlib.actuator.dummyactuator import DummyActuator


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
# SHUTDOWN FLAG
# -------------------------
shutdown_event = asyncio.Event()


def request_shutdown():
    logger.info("Shutdown signal received")
    shutdown_event.set()


# -------------------------
# ACTUATOR CONFIGURATION
# -------------------------
# All joints are velocity-controlled (deg/sec)
ACTUATORS = [
    ("J1", DummyActuator("J1")),
    ("J2", DummyActuator("J2")),
    ("J3", MyActuator("J3", 0x142)),
    ("J4", ODriveActuator("J4", 0x4)),
    ("J5", MyActuator("J5", 0x143)),
    ("J6", MyActuator("J6", 0x144)),
]

manager: ActuatorManager | None = None

# Store commanded velocities (deg/sec)
commanded_inputs: dict[str, float] = {
    joint: 0.0 for joint, _ in ACTUATORS
}


# -------------------------
# INPUT CALLBACK FACTORY
# -------------------------
def make_input_callback(joint_name: str):
    async def callback(value: float):
        commanded_inputs[joint_name] = value
    return callback


# -------------------------
# CONTROL LOOP
# -------------------------
async def control_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():
        for joint, actuator in ACTUATORS:
            target_deg_per_sec = commanded_inputs[joint]

            # ODrive expects turns/sec
            if isinstance(actuator, ODriveActuator):
                actuator.set_velocity(target_deg_per_sec / 360.0)
            else:
                actuator.set_velocity(target_deg_per_sec)

            # Publish commanded velocity
            await control_socket.outputs.update_output(
                f"{joint}_velocity_cmd",
                target_deg_per_sec,
            )

        await asyncio.sleep(interval)


# -------------------------
# HEARTBEAT LOOP
# -------------------------
async def heartbeat_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():
        await control_socket.outputs.update_output("heartbeat", True)
        await asyncio.sleep(interval)


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
    # CAN Setup
    # -------------------------
    can_client = CANClient()
    await can_client.start()

    manager = ActuatorManager(can_client, rate_hz=50.0)

    for _, actuator in ACTUATORS:
        manager.register(actuator)

    asyncio.create_task(manager.loop())

    # Arm ODrive actuators
    for _, actuator in ACTUATORS:
        if isinstance(actuator, ODriveActuator):
            actuator.request_arm()

    # -------------------------
    # WebSocket Setup
    # -------------------------
    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    # Register velocity inputs (deg/sec)
    for joint, _ in ACTUATORS:
        schema.register_axis(
            control_socket.inputs,
            joint,
            callback=lambda v, name=joint: asyncio.create_task(
                make_input_callback(name)(v)
            ),
        )

    # Register outputs
    for joint, _ in ACTUATORS:
        control_socket.outputs.register_output(f"{joint}_velocity_cmd")

    control_socket.outputs.register_output("heartbeat")

    await control_socket.start()

    logger.info(f"Velocity control running on ws://{ws_host}:{ws_port}")

    control_task = asyncio.create_task(
        control_loop(control_socket, status_interval)
    )
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(control_socket, heartbeat_interval)
    )

    await shutdown_event.wait()

    # -------------------------
    # SAFE STOP
    # -------------------------
    logger.info("Stopping actuators")

    for _, actuator in ACTUATORS:
        actuator.set_velocity(0.0)
        if isinstance(actuator, ODriveActuator):
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
    parser.add_argument("--ws_name", type=str, default="velocity_control")
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