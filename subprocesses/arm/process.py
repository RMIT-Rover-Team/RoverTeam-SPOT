import asyncio
import argparse
import json
import logging
from typing import Dict

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema
from sharedlib.canbus.client import CANClient

from sharedlib.actuator.actuator_manager import ActuatorManager
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
logger.setLevel(logging.DEBUG)
logger.addHandler(JsonHandler())


# -------------------------
# ACTUATOR LIST (NEW STYLE)
# -------------------------
ACTUATORS = [
    MyActuator("axis_roll", 0x144),
    MyActuator("axis_pitch", 0x143),
    MyActuator("axis_yaw", 0x142),

    DummyActuator("axis_x"),
    DummyActuator("axis_y"),
    DummyActuator("axis_z"),
]


# -------------------------
# GLOBAL STATE
# -------------------------
actuators: Dict[str, object] = {}
manager: ActuatorManager | None = None


# -------------------------
# AXIS CALLBACK
# -------------------------
async def handle_axis(axis_name: str, value: float):
    actuator = actuators.get(axis_name)
    if actuator:
        actuator.set_velocity(value)


# -------------------------
# TELEMETRY LOOP
# -------------------------
async def telemetry_loop(control_socket: ControlSocket, interval: float):
    while True:
        for actuator in ACTUATORS:
            name = actuator.name

            # Continuously integrate dummy actuators
            if isinstance(actuator, DummyActuator):
                await actuator.update()

            vel = getattr(actuator, "velocity", 0.0)
            pos = getattr(actuator, "position", 0.0)

            await control_socket.outputs.update_output(f"{name}_vel", vel)
            await control_socket.outputs.update_output(f"{name}_pos", pos)

        await asyncio.sleep(interval)


# -------------------------
# HEARTBEAT LOOP
# -------------------------
async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# MAIN
# -------------------------
async def main(
    ws_host: str,
    ws_port: int,
    ws_name: str,
    heartbeat: float,
    status_interval: float,
):
    global manager

    # -------------------------
    # CAN CLIENT
    # -------------------------
    can_client = CANClient()
    await can_client.start()

    # -------------------------
    # ACTUATOR MANAGER
    # -------------------------
    manager = ActuatorManager(can_client, rate_hz=20.0)

    for actuator in ACTUATORS:
        actuators[actuator.name] = actuator

        # Only register real CAN actuators with manager
        if isinstance(actuator, MyActuator):
            manager.register(actuator)

    asyncio.create_task(manager.loop())

    # -------------------------
    # CONTROL SOCKET
    # -------------------------
    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    for actuator in ACTUATORS:
        axis_name = actuator.name

        schema.register_axis(
            control_socket.inputs,
            axis_name,
            callback=lambda v, axis=axis_name: handle_axis(axis, v),
        )

        control_socket.outputs.register_output(f"{axis_name}_vel")
        control_socket.outputs.register_output(f"{axis_name}_pos")

    await control_socket.start()
    logger.info(
        f"ControlSocket running on ws://{ws_host}:{ws_port} as '{ws_name}'"
    )

    tasks = [
        asyncio.create_task(heartbeat_loop(heartbeat)),
        asyncio.create_task(telemetry_loop(control_socket, status_interval)),
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutdown received")
    finally:
        for t in tasks:
            t.cancel()

        await asyncio.sleep(0)
        await control_socket.stop()
        await can_client.close()


# -------------------------
# ENTRYPOINT
# -------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=8766)
    parser.add_argument("--ws_name", type=str, default="arm")
    parser.add_argument("--heartbeat", type=float, default=10)
    parser.add_argument("--status_interval", type=float, default=0.5)

    args = parser.parse_args()

    asyncio.run(
        main(
            args.ws_host,
            args.ws_port,
            args.ws_name,
            args.heartbeat,
            args.status_interval,
        )
    )