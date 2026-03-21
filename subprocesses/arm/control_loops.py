# control_loops.py

import asyncio
from kinematics.util import closest_multi_turn_target, shortest_angle_delta, clamp
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

        # -------------------------------------------------
        # Integrate IK cartesian position (mm space)
        # -------------------------------------------------
        commanded_inputs["ik_z_pos"] += commanded_inputs["ik_z_vel"] * dt
        commanded_inputs["ik_x_pos"] += commanded_inputs["ik_x_vel"] * dt

        move_input = commanded_inputs.get("moveto_ready", 0)
        move_mode = int(move_input) if move_input > 0.5 else 0

        # =================================================
        # IK MODE (absolute position control)
        # =================================================
        if move_mode == MOVETO_IK:

            ik_target = [
                commanded_inputs["ik_x_pos"] / 1000.0,
                0,
                commanded_inputs["ik_z_pos"] / 1000.0,
            ]

            solve_ik(arm_model.joints, arm_model.links, ik_target)

            j2_raw = arm_model.joints[1].angle_deg
            j3_raw = -arm_model.joints[2].angle_deg

            for joint, actuator in actuators:

                if joint == "J2":
                    current = actuator.get_position()
                    target = closest_multi_turn_target(current, j2_raw)
                    actuator.set_position(target)

                    await control_socket.outputs.update_output(
                        "J2_position_cmd", target
                    )

                elif joint == "J3":
                    current = actuator.get_position()
                    target = closest_multi_turn_target(current, j3_raw)
                    actuator.set_position(target)

                    await control_socket.outputs.update_output(
                        "J3_position_cmd", target
                    )

                else:
                    vel = commanded_inputs.get(joint, 0.0)
                    actuator.set_velocity(vel)

        # =================================================
        # PRESET MOVE MODES (READY / STOW)
        # =================================================
        elif move_mode in MOVETO_POSITIONS:

            move_target = MOVETO_POSITIONS[move_mode]

            for joint, actuator in actuators:

                if joint in move_target:
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
                else:
                    vel = commanded_inputs.get(joint, 0.0)
                    actuator.set_velocity(vel)

        # =================================================
        # NORMAL MANUAL VELOCITY MODE
        # =================================================
        else:
            for joint, actuator in actuators:
                vel = commanded_inputs.get(joint, 0.0)

                if isinstance(actuator, ODriveActuator):
                    actuator.set_velocity(vel / 360.0)
                else:
                    actuator.set_velocity(vel)

                await control_socket.outputs.update_output(
                    f"{joint}_velocity_cmd",
                    vel,
                )

        await asyncio.sleep(interval)


# ---------------------------------------------------------
# HEARTBEAT LOOP
# ---------------------------------------------------------
async def heartbeat_loop(shutdown_event, interval: float):
    while not shutdown_event.is_set():
        print("HEARTBEAT", flush=True)
        await asyncio.sleep(interval)


# ---------------------------------------------------------
# TELEMETRY LOOP
# ---------------------------------------------------------
async def telemetry_loop(actuators, control_socket, shutdown_event, interval: float):
    while not shutdown_event.is_set():
        for joint, actuator in actuators:
            try:
                pos = actuator.get_position()
                vel = actuator.get_velocity()

                await control_socket.outputs.update_output(
                    f"{joint}_position", pos
                )
                await control_socket.outputs.update_output(
                    f"{joint}_velocity", vel
                )

            except Exception as e:
                print(f"Telemetry failed for {joint}: {e}")

        await asyncio.sleep(interval)