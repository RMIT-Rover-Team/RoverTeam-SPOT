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
from sharedlib.actuator.payloadActuator import PayloadActuator

from kinematics.differential_velocity import DifferentialVelocityController

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
# INPUT CALLBACK FACTORY
# -------------------------
def make_input_callback(joint_name: str, commanded_inputs: dict):
    async def callback(value: float):
        commanded_inputs[joint_name] = value
    return callback


# -------------------------
# CONTROL LOOP
# -------------------------
async def control_loop(actuators, commanded_inputs, controllers, control_socket: ControlSocket, interval: float):
    last_time = asyncio.get_event_loop().time()

    while not shutdown_event.is_set():
        now = asyncio.get_event_loop().time()
        dt = now - last_time
        last_time = now

        for joint, actuator in actuators:
            measured_pos = actuator.get_position()
            input_velocity = commanded_inputs[joint]  # deg/s

            velocity_cmd = controllers[joint].update(
                measured_position=measured_pos,
                commanded_velocity=input_velocity,
                dt=dt,
            )

            # ODrive expects turns/s
            if isinstance(actuator, ODriveActuator):
                actuator.set_velocity(velocity_cmd / 360.0)
            else:
                actuator.set_velocity(velocity_cmd)

            await control_socket.outputs.update_output(
                f"{joint}_velocity_cmd",
                velocity_cmd,
            )

        await asyncio.sleep(interval)


# -------------------------
# HEARTBEAT LOOP
# -------------------------
async def heartbeat_loop(control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():
        print("HEARTBEAT") # THIS IS REQUIRED FOR PROCESS WATCHDOG - DO NOT REMOVE
        await asyncio.sleep(interval)


# -------------------------
# TELEMETRY LOOP (POSITION + VELOCITY)
# -------------------------
async def telemetry_loop(actuators, control_socket: ControlSocket, interval: float):
    while not shutdown_event.is_set():
        for joint, actuator in actuators:
            try:
                pos = actuator.get_position()  # implement in each actuator
                vel = actuator.get_velocity()  # implement in each actuator
                await control_socket.outputs.update_output(f"{joint}_position", pos)
                await control_socket.outputs.update_output(f"{joint}_velocity", vel)
            except Exception as e:
                logger.warning(f"Telemetry read failed for {joint}: {e}")
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
    telemetry_interval: float = 0.1,
    dev: bool = False,
):
    # -------------------------
    # ACTUATORS
    # -------------------------
    if dev:
        actuators = [
            ("J1", DummyActuator("J1")),
            ("J2", DummyActuator("J2")),
            ("J3", DummyActuator("J3")),
            ("J4", DummyActuator("J4")),
            ("J5", DummyActuator("J5")),
            ("J6", DummyActuator("J6")),
            ("Grip", DummyActuator("Grip")),
            ("Poke", DummyActuator("Poke")),
        ]
    else:
        actuators = [
            ("J1", DummyActuator("J1")),
            ("J2", MyActuator("J2", 0x141)),
            ("J3", MyActuator("J3", 0x142)),
            ("J4", ODriveActuator("J4", 0x15)),
            ("J5", MyActuator("J5", 0x143)),
            ("J6", MyActuator("J6", 0x144)),
            ("Grip", PayloadActuator("Grip", 0)),
            ("Poke", PayloadActuator("Poke", 1)),
        ]

    commanded_inputs = {joint: 0.0 for joint, _ in actuators}

    controllers = {
        joint: DifferentialVelocityController(max_speed_deg_s=100.0)
        for joint, _ in actuators
    }

    # -------------------------
    # LOOP AND SIGNALS
    # -------------------------
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # -------------------------
    # CAN CLIENT
    # -------------------------
    can_client = CANClient()
    await can_client.start()

    manager = ActuatorManager(can_client, rate_hz=50.0)
    for _, actuator in actuators:
        manager.register(actuator)

    # -------------------------
    # WEBSOCKET SETUP
    # -------------------------
    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    # Register velocity inputs
    for joint, _ in actuators:
        schema.register_axis(
            control_socket.inputs,
            joint,
            callback=lambda v, name=joint: asyncio.create_task(
                make_input_callback(name, commanded_inputs)(v)
            ),
        )

    # Register outputs
    for joint, _ in actuators:
        control_socket.outputs.register_output(f"{joint}_velocity_cmd")
        control_socket.outputs.register_output(f"{joint}_position")
        control_socket.outputs.register_output(f"{joint}_velocity")

    await control_socket.start()
    logger.info(f"Velocity control running on ws://{ws_host}:{ws_port}")

    # -------------------------
    # CREATE TASKS ARRAY
    # -------------------------
    tasks = [
        asyncio.create_task(manager.loop(), name="manager_loop"),
        asyncio.create_task(control_loop(actuators, commanded_inputs, controllers, control_socket, status_interval), name="control_loop"),
        asyncio.create_task(heartbeat_loop(control_socket, heartbeat_interval), name="heartbeat_loop"),
        asyncio.create_task(telemetry_loop(actuators, control_socket, telemetry_interval), name="telemetry_loop"),
    ]

    # Arm ODrive actuators
    for _, actuator in actuators:
        if isinstance(actuator, ODriveActuator):
            actuator.request_arm()

    # -------------------------
    # WAIT FOR SHUTDOWN
    # -------------------------
    await shutdown_event.wait()

    logger.info("Shutting down tasks...")

    # Cancel all tasks
    for t in tasks:
        t.cancel()

    # Await cancellation
    await asyncio.gather(*tasks, return_exceptions=True)

    # -------------------------
    # SAFE STOP ACTUATORS
    # -------------------------
    logger.info("Stopping actuators")
    for _, actuator in actuators:
        actuator.set_velocity(0.0)
        if isinstance(actuator, ODriveActuator):
            actuator.request_disarm()

    # -------------------------
    # CLEANUP
    # -------------------------
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
    parser.add_argument("--telemetry_interval", type=float, default=0.1, help="Telemetry interval in seconds")
    parser.add_argument("--dev", action="store_true", default=False, help="Enable developer mode")

    args = parser.parse_args()

    asyncio.run(
        main(
            args.ws_host,
            args.ws_port,
            args.ws_name,
            args.status_interval,
            args.heartbeat,
            telemetry_interval=args.telemetry_interval,
            dev=args.dev,
        )
    )