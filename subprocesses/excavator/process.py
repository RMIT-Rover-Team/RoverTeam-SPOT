import asyncio
import argparse
import json
import logging
import signal
from pathlib import Path

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema
from sharedlib.canbus.client import CANClient
from sharedlib.actuator.actuator_manager import ActuatorManager

from sharedlib.actuator.dummyactuator import DummyActuator
from sharedlib.actuator.payloadActuator import PayloadActuator



from control_loops import (
    control_loop,
    heartbeat_loop,
    telemetry_loop,
)




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
            ("EXC1", DummyActuator("EXC1")),
            ("EXC2", DummyActuator("EXC2"))
        ]
    else:
        actuators = [
            ("EXC1", PayloadActuator("EXC1", 0)),
            ("EXC2", PayloadActuator("EXC2", 1))
        ]

    commanded_inputs = {joint: 0.0 for joint, _ in actuators}
    control_modes = {joint: 0 for joint, _ in actuators}


    # -------------------------
    # SIGNAL HANDLERS
    # -------------------------
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # -------------------------
    # CAN CLIENT
    # -------------------------
    can_client = CANClient()
    await can_client.start()

    manager = ActuatorManager(can_client, rate_hz=10.0)
    for _, actuator in actuators:
        manager.register(actuator)

    # -------------------------
    # WEBSOCKET
    # -------------------------
    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    # Register joint velocity inputs
    for joint, _ in actuators:
        schema.register_axis(
            control_socket.inputs,
            joint,
            callback=lambda v, name=joint: asyncio.create_task(
                make_input_callback(name, commanded_inputs)(v)
            ),
        )


    # -------------------------
    
    # -------------------------
    # REGISTER OUTPUTS
    # -------------------------
    for joint, _ in actuators:
        control_socket.outputs.register_output(f"{joint}_velocity_cmd")
        control_socket.outputs.register_output(f"{joint}_position")
        control_socket.outputs.register_output(f"{joint}_velocity")

    await control_socket.start()
    logger.info(f"Control running on ws://{ws_host}:{ws_port}")

    # -------------------------
    # TASKS
    # -------------------------
    tasks = [
        asyncio.create_task(manager.loop(), name="manager_loop"),
        asyncio.create_task(
            control_loop(
                actuators,
                commanded_inputs,
                control_modes,
                control_socket,
                shutdown_event,
                status_interval,
            ),
            name="control_loop",
        ),
        asyncio.create_task(
            heartbeat_loop(shutdown_event, heartbeat_interval),
            name="heartbeat_loop",
        ),
        asyncio.create_task(
            telemetry_loop(
                actuators,
                control_socket,
                shutdown_event,
                telemetry_interval,
            ),
            name="telemetry_loop",
        ),
    ]

    # -------------------------
    # WAIT FOR SHUTDOWN
    # -------------------------
    await shutdown_event.wait()

    logger.info("Shutting down tasks...")

    for t in tasks:
        t.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    # -------------------------
    # SAFE STOP
    # -------------------------
    logger.info("Stopping actuators")
    for _, actuator in actuators:
        actuator.set_velocity(0.0)

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
    parser.add_argument("--telemetry_interval", type=float, default=0.1)
    parser.add_argument("--dev", action="store_true", default=False)

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