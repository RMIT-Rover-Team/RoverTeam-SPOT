import asyncio
import argparse
import json
import logging
import time
from typing import Dict

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
logger.setLevel(logging.DEBUG)
logger.addHandler(JsonHandler())


# -------------------------
# ARM CONFIG (NEW STYLE)
# -------------------------
ACTUATORS = [
    {"name": "axis_roll",  "id": 0x144, "type": "myactuator"},
    {"name": "axis_pitch", "id": 0x143, "type": "myactuator"},
    {"name": "axis_yaw",   "id": 0x142, "type": "myactuator"},
    
    {"name": "axis_x", "id": None, "type": None},
    {"name": "axis_y", "id": None, "type": None},
    {"name": "axis_z", "id": None, "type": None},
]


# -------------------------
# GLOBAL STATE
# -------------------------
axis_targets: Dict[str, float] = {}
axis_last_update: Dict[str, float] = {}

actuators: Dict[str, MyActuator] = {}
manager: ActuatorManager | None = None


# -------------------------
# AXIS CALLBACK
# -------------------------
async def handle_axis(axis_name: str, value: float):
    axis_targets[axis_name] = value
    axis_last_update[axis_name] = time.time()

    actuator = actuators.get(axis_name)

    # If axis has no hardware bound, safely return
    if actuator is None:
        return

    actuator.set_velocity(value)


# -------------------------
# TELEMETRY LOOP
# -------------------------
async def telemetry_loop(control_socket: ControlSocket, interval: float):
    while True:
        for config in ACTUATORS:
            name = config["name"]
            actuator = actuators.get(name)

            vel = axis_targets.get(name, 0.0)
            pos = actuator.position if actuator else 0.0

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

    # Register actuators (only real hardware)
    for config in ACTUATORS:
        if config["type"] != "myactuator":
            continue

        actuator = MyActuator(config["name"], config["id"])
        actuators[config["name"]] = actuator
        manager.register(actuator)

    # Start manager loop
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

    # Register ALL axis handlers (including x/y/z)
    for config in ACTUATORS:
        axis_name = config["name"]

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