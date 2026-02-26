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


# -------------------------
# ACTUATOR CONFIGURATION
# -------------------------
# Each entry: (actuator instance, input name)
ACTUATORS = [
    (ODriveActuator("J4", 0x4), "pitch"),   # ODrive actuator
    (MyActuator("J3", 0x142), "z"),         # MyActuator
]

manager: ActuatorManager | None = None

# Store current commanded values per input
commanded_inputs: dict[str, float] = {name: 0.0 for _, name in ACTUATORS}


# -------------------------
# INPUT CALLBACK
# -------------------------
def make_input_callback(input_name: str):
    async def callback(value: float):
        commanded_inputs[input_name] = value
    return callback


# -------------------------
# CONTROL LOOP
# -------------------------
async def control_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():
        for actuator, input_name in ACTUATORS:
            target = commanded_inputs[input_name]

            # Convert deg/sec -> turns/sec for ODrive
            if isinstance(actuator, ODriveActuator):
                target_turns = target / 360.0
                actuator.set_velocity(target_turns)
            else:
                actuator.set_velocity(target)

            # Update outputs
            await control_socket.outputs.update_output(
                f"{input_name}_velocity_cmd",
                target,
            )

        await asyncio.sleep(interval)


# -------------------------
# HEARTBEAT LOOP
# -------------------------
async def heartbeat_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():
        print("HEARTBEAT")
        await control_socket.outputs.update_output("heartbeat", True)
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
async def main(ws_host: str, ws_port: int, ws_name: str,
               status_interval: float, heartbeat_interval: float):
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
    for actuator, _ in ACTUATORS:
        manager.register(actuator)
    asyncio.create_task(manager.loop())

    # Arm any ODrive actuators
    for actuator, _ in ACTUATORS:
        if isinstance(actuator, ODriveActuator):
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

    # Register all input callbacks
    for _, input_name in ACTUATORS:
        schema.register_axis(
            control_socket.inputs,
            input_name,
            callback=lambda v, name=input_name: asyncio.create_task(
                make_input_callback(name)(v)
            ),
        )

    # Register outputs
    for _, input_name in ACTUATORS:
        control_socket.outputs.register_output(f"{input_name}_velocity_cmd")
    control_socket.outputs.register_output("heartbeat")

    await control_socket.start()

    logger.info(f"Velocity control running on ws://{ws_host}:{ws_port}")

    control_task = asyncio.create_task(control_loop(control_socket, status_interval))
    heartbeat_task = asyncio.create_task(heartbeat_loop(control_socket, heartbeat_interval))

    await shutdown_event.wait()

    # -------------------------
    # Safe stop
    # -------------------------
    for actuator, _ in ACTUATORS:
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

    asyncio.run(main(
        args.ws_host,
        args.ws_port,
        args.ws_name,
        args.status_interval,
        args.heartbeat,
    ))