import asyncio
import argparse
import json
import logging
import time
import math
from typing import Dict

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema
from sharedlib.canbus.client import CANClient

from sharedlib.actuator.actuator_manager import ActuatorManager
from sharedlib.actuator.myactuator import MyActuator
from sharedlib.actuator.dummyactuator import DummyActuator

from kinematics.ik import RobotArm6DOF
from kinematics.util import closest_equivalent_angle


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
# ROBOT GEOMETRY (DEFINE YOUR ARM HERE)
# -------------------------
robot = RobotArm6DOF(
    d1=0.020,        # base to J2
    a1=0.0,          # no horizontal offset
    a2=0.400,        # link2
    a3=0.400,        # link3
    d4=0.020,        # wrist offset
    d7=0.060,        # final tool length
    joint_directions=[1, 1, 1, 1, 1, 1],
)


# -------------------------
# ACTUATORS
# -------------------------
ACTUATORS = [
    MyActuator("J1", 0x142),
    MyActuator("J2", 0x143),
    MyActuator("J3", 0x144),
    DummyActuator("J4"),
    DummyActuator("J5"),
    DummyActuator("J6"),
]

actuators: Dict[str, object] = {}
manager: ActuatorManager | None = None


# -------------------------
# GLOBAL STATE
# -------------------------
# Desired end-effector pose (mm + degrees externally)
desired_position = {
    "x": 400.0,
    "y": 0.0,
    "z": 100.0,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
}

velocity_inputs = {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
}

last_time = time.time()
last_joint_targets = [0.0] * 6

# -------------------------
# AXIS CALLBACK
# -------------------------
async def handle_axis(axis_name: str, value: float):
    velocity_inputs[axis_name] = value


# -------------------------
# TELEMETRY + IK LOOP
# -------------------------
# -------------------------
# TELEMETRY + IK LOOP
# -------------------------
async def telemetry_loop(control_socket: ControlSocket, interval: float):
    global last_time

    while True:
        now = time.time()
        dt = now - last_time
        last_time = now

        # integrate velocities (mm/s and deg/s)
        for key in desired_position.keys():
            desired_position[key] += velocity_inputs[key] * dt

        # ---- Convert units for IK ----
        x = desired_position["x"] / 1000.0
        y = desired_position["y"] / 1000.0
        z = desired_position["z"] / 1000.0

        roll = math.radians(desired_position["roll"])
        pitch = math.radians(desired_position["pitch"])
        yaw = math.radians(desired_position["yaw"])

        try:
            joint_angles_rad, success, achievable_pos = robot.inverse_kin(
                x, y, z, roll, pitch, yaw
            )

            # Update desired_position with achievable position (clamped)
            desired_position["x"] = achievable_pos[0] * 1000.0
            desired_position["y"] = achievable_pos[1] * 1000.0
            desired_position["z"] = achievable_pos[2] * 1000.0

            if not success:
                logger.warning(
                    f"Target unreachable, moving to closest achievable position: "
                    f"x={desired_position['x']:.1f}mm, "
                    f"y={desired_position['y']:.1f}mm, "
                    f"z={desired_position['z']:.1f}mm"
                )

        except Exception as e:
            logger.error(f"IK failed: {e}")
            await asyncio.sleep(interval)
            continue

        # Convert radians → degrees for actuators
        joint_angles_deg = [
            math.degrees(a) if not math.isnan(a) else 0.0
            for a in joint_angles_rad
        ]

        # Apply to actuators
        for i, (actuator, angle) in enumerate(zip(ACTUATORS, joint_angles_deg)):

            continuous_angle = closest_equivalent_angle(
                angle,
                last_joint_targets[i]
            )

            last_joint_targets[i] = continuous_angle

            logger.debug(f"Setting {actuator.name} to {continuous_angle:.2f} deg")

            actuator.set_position(continuous_angle)

        # Send telemetry
        for actuator in ACTUATORS:
            pos = actuator.target_position
            vel = actuator.get_velocity()

            await control_socket.outputs.update_output(
                f"{actuator.name}_pos", pos
            )
            await control_socket.outputs.update_output(
                f"{actuator.name}_vel", vel
            )

        # Output current desired (or clamped) position
        for pos in ["x", "y", "z", "roll", "pitch", "yaw"]:
            await control_socket.outputs.update_output(
                f"{pos}_pos", desired_position[pos]
            )

        await control_socket.outputs.update_output("ik_success", success)

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

    can_client = CANClient()
    await can_client.start()

    manager = ActuatorManager(can_client, rate_hz=20.0)

    for actuator in ACTUATORS:
        actuators[actuator.name] = actuator
        manager.register(actuator)

    asyncio.create_task(manager.loop())

    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    # Register velocity inputs
    for axis_name in velocity_inputs.keys():
        schema.register_axis(
            control_socket.inputs,
            axis_name,
            callback=lambda v, axis=axis_name:
                asyncio.create_task(handle_axis(axis, v)),
        )

    # Register outputs
    for actuator in ACTUATORS:
        control_socket.outputs.register_output(f"{actuator.name}_pos")
        control_socket.outputs.register_output(f"{actuator.name}_vel")

    for pos in desired_position.keys():
        control_socket.outputs.register_output(f"{pos}_pos")

    control_socket.outputs.register_output("ik_success", "bool")

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