# control_loops.py

import asyncio
from kinematics.util import shortest_angle_delta, clamp
from kinematics.ik import solve_ik
from sharedlib.actuator.odrive import ODriveActuator

MOVETO_READY = 1
MOVETO_STOW = 2
MOVETO_IK = 3

MOVETO_POSITIONS = {
    MOVETO_READY: {
        "J2": -135,
        "J3": -135,
    },
    MOVETO_STOW: {
        "J2": 0,
        "J3": 0,
    },
    MOVETO_IK: {
        "J2": None,
        "J3": None,
    },
}


async def control_loop(
    actuators,
    commanded_inputs,
    control_modes,
    arm_model,
    control_socket,
    shutdown_event,
    interval: float,
):
    last_time = asyncio.get_event_loop().time()

    while not shutdown_event.is_set():
        now = asyncio.get_event_loop().time()
        dt = now - last_time
        last_time = now

        # -------------------------
        # Update IK positions (mm)
        # -------------------------
        commanded_inputs["ik_z_pos"] += commanded_inputs["ik_z_vel"] * dt
        commanded_inputs["ik_x_pos"] += commanded_inputs["ik_x_vel"] * dt

        # -------------------------
        # Determine move mode
        # -------------------------
        move_input = commanded_inputs.get("moveto_ready", 0)
        move_input_enum = int(move_input) if move_input > 0.5 else 0

        move_target = {}

        if move_input_enum in MOVETO_POSITIONS:
            move_target = MOVETO_POSITIONS[move_input_enum].copy()

            # IK dynamic position update
            if move_input_enum == MOVETO_IK:
                ik_target = [
                    commanded_inputs["ik_x_pos"] / 1000.0,  # mm -> m
                    0,
                    commanded_inputs["ik_z_pos"] / 1000.0,
                ]

                solve_ik(arm_model.joints, arm_model.links, ik_target)

                # J2 / J3 only
                move_target["J2"] = arm_model.joints[1].angle_deg
                move_target["J3"] = -arm_model.joints[2].angle_deg

            # Enable diff-pos mode
            for joint in move_target.keys():
                control_modes[joint] = 1
        else:
            for joint in ["J2", "J3"]:
                control_modes[joint] = 0

        # -------------------------
        # Actuator Control
        # -------------------------
        for joint, actuator in actuators:
            velocity_cmd = 0.0
            mode = control_modes.get(joint, 0)

            if mode == 0:
                velocity_cmd = commanded_inputs[joint]
            elif joint in move_target:
                target_pos = move_target[joint]
                current_pos = actuator.get_position()
                velocity_cmd = clamp(
                    shortest_angle_delta(current_pos, target_pos),
                    -10,
                    10,
                )

            if isinstance(actuator, ODriveActuator):
                actuator.set_velocity(velocity_cmd / 360.0)
            else:
                actuator.set_velocity(velocity_cmd)

            await control_socket.outputs.update_output(
                f"{joint}_velocity_cmd",
                velocity_cmd,
            )

        await asyncio.sleep(interval)


async def heartbeat_loop(shutdown_event, interval: float):
    while not shutdown_event.is_set():
        print("HEARTBEAT")  # watchdog requirement
        await asyncio.sleep(interval)


async def telemetry_loop(actuators, control_socket, shutdown_event, interval: float):
    while not shutdown_event.is_set():
        for joint, actuator in actuators:
            try:
                pos = actuator.get_position()
                vel = actuator.get_velocity()
                await control_socket.outputs.update_output(f"{joint}_position", pos)
                await control_socket.outputs.update_output(f"{joint}_velocity", vel)
            except Exception as e:
                print(f"Telemetry failed for {joint}: {e}")
        await asyncio.sleep(interval)