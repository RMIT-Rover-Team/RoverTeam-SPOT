# control_loops.py

import asyncio


async def control_loop(
    actuators,
    commanded_inputs,
    control_socket,
    shutdown_event,
    interval: float,
):
    while not shutdown_event.is_set():

        # =================================================
        # NORMAL MANUAL VELOCITY MODE
        # =================================================
        for joint, actuator in actuators:
            vel = commanded_inputs.get(joint, 0.0)

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
        print("HEARTBEAT")
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