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
from sharedlib.actuator.dummyactuator import DummyActuator

from kinematics.ik import solve_ik  # our IK solver

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
# ACTUATOR LIST
# -------------------------
# J1,2,3 are dummy (cartesian integrators)
# J4,5,6 are MyActuator
ACTUATORS = [
    MyActuator("J1", 0x142),
    MyActuator("J2", 0x143),
    MyActuator("J3", 0x144),
    DummyActuator("J4"),
    DummyActuator("J5"),
    DummyActuator("J6"),
]

# -------------------------
# GLOBAL STATE
# -------------------------
actuators: Dict[str, object] = {}
manager: ActuatorManager | None = None

# Desired end-effector position in mm and degrees
desired_position = {"x": 400.0, "y": 0.0, "z": 200.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
last_time = time.time()

# Velocity inputs in mm/s or deg/s (from control socket)
velocity_inputs = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}

# -------------------------
# AXIS CALLBACK
# -------------------------
async def handle_axis(axis_name: str, value: float):
    velocity_inputs[axis_name] = value

# -------------------------
# TELEMETRY + IK LOOP
# -------------------------
async def telemetry_loop(control_socket: ControlSocket, interval: float):
    global last_time
    while True:
        now = time.time()
        dt = now - last_time
        last_time = now

        # integrate velocity inputs to desired position
        desired_position["x"] += velocity_inputs["x"] * dt
        desired_position["y"] += velocity_inputs["y"] * dt
        desired_position["z"] += velocity_inputs["z"] * dt
        desired_position["roll"] += velocity_inputs["roll"] * dt
        desired_position["pitch"] += velocity_inputs["pitch"] * dt
        desired_position["yaw"] += velocity_inputs["yaw"] * dt

        # compute IK for desired position
        joint_angles = solve_ik(
            desired_position["x"],
            desired_position["y"],
            desired_position["z"],
            desired_position["roll"],
            desired_position["pitch"],
            desired_position["yaw"]
        )

        # apply angles to actuators
        for actuator, angle in zip(ACTUATORS, joint_angles):

            #debug logging
            logger.debug(f"Setting {actuator.name} to {angle:.2f} degrees")

            actuator.set_position(angle)

        # send telemetry
        for actuator in ACTUATORS:
            pos = actuator.target_position
            vel = actuator.get_velocity()
            await control_socket.outputs.update_output(f"{actuator.name}_pos", pos)
            await control_socket.outputs.update_output(f"{actuator.name}_vel", vel)

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

    # register inputs for cartesian velocities
    for axis_name in velocity_inputs.keys():
        schema.register_axis(
            control_socket.inputs,
            axis_name,
            callback=lambda v, axis=axis_name: asyncio.create_task(handle_axis(axis, v)),
        )
    
    for actuator in ACTUATORS:
        control_socket.outputs.register_output(f"{actuator.name}_pos")
        control_socket.outputs.register_output(f"{actuator.name}_vel")

    await control_socket.start()
    logger.info(f"ControlSocket running on ws://{ws_host}:{ws_port} as '{ws_name}'")

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
    parser.add_argument("--status_interval", type=float, default=0.05)

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