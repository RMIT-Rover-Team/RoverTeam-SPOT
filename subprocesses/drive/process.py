import asyncio
import argparse
import json
import logging
import signal

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema

import driveStackBinaries.torque as torque

import imu.imu as imu

#The status indicator
import sharedlib.utilities.StatusIndicator as Status

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

def make_input_callback(name: str, commanded_inputs: dict):
    async def callback(value: float):
        commanded_inputs[name] = value
    return callback

def calc_drive(x: float, y: float):
    drive_l = y + x
    drive_r = y - x

    # normalize if either exceeds magnitude 1
    max_mag = max(1.0, abs(drive_l), abs(drive_r))
    drive_l /= max_mag
    drive_r /= max_mag

    return drive_l, drive_r

# -------------------------
# CONTROL LOOP (placeholder)
# -------------------------

async def control_loop(
    commanded_inputs,
    control_socket,
    torqueController,
    shutdown_event,
    interval,
):
    while not shutdown_event.is_set():

        drive_mode = int(commanded_inputs["drive_mode"])

        drive_multiplier = commanded_inputs["drive_multiplier"]

        if drive_mode == 2:
            drive_multiplier = -1

        drive_l, drive_r = calc_drive(commanded_inputs["drive_x"], commanded_inputs["drive_y"])

        drive_l *= drive_multiplier
        drive_r *= drive_multiplier

        torqueController.set_speed(drive_l, drive_r)

        await asyncio.sleep(interval)


# -------------------------
# HEARTBEAT
# -------------------------

async def heartbeat_loop(shutdown_event, interval):
    while not shutdown_event.is_set():
        print("HEARTBEAT")
        await asyncio.sleep(interval)
        

async def make_drive_mode_event(torqueController, control_socket, mode: int, commanded_inputs: dict):
    commanded_inputs["drive_mode"] = mode

    modeMap = [
        torque.UNLOCKED_VELOCITY,
        torque.LOCKED_VELOCITY,
        torque.UNLOCKED_TORQUE
    ]

    logger.warning(f"SWITCHED TO MODE: {mode}")

    torqueController.set_mode(modeMap[mode])
    await control_socket.outputs.update_output("drive_mode", mode)

async def error_clear_event(torqueController):
    torqueController.enable()

async def control_change(hasControl):
    if hasControl:
        Status.setLED(Status.LEDCOLOUR.MOTION)
    else:
        Status.setLED(Status.LEDCOLOUR.LOCKED)

# -------------------------
# MAIN
# -------------------------

async def main(
    ws_host: str,
    ws_port: int,
    ws_name: str,
    status_interval: float,
    heartbeat_interval: float,
):

    # -------------------------
    # INPUT STATE
    # -------------------------

    torqueController = torque.TorqueHandler("can0")
    torqueController.set_mode(torque.LOCKED_VELOCITY)
    torqueController.enable()

    commanded_inputs = {
        "drive_x": 0.0,
        "drive_y": 0.0,
        "drive_mode": 0,
        "drive_multiplier": 200
    }

    # -------------------------
    # SIGNAL HANDLERS
    # -------------------------

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # -------------------------
    # CONTROL SOCKET
    # -------------------------

    control_socket = ControlSocket(
        ws_host,
        ws_port,
        ws_name,
        allow_multiple_clients=False,
    )

    # -------------------------
    # REGISTER INPUTS
    # -------------------------

    schema.register_axis(
        control_socket.inputs,
        "drive_x",
        callback=lambda v: asyncio.create_task(
            make_input_callback("drive_x", commanded_inputs)(v)
        ),
    )

    schema.register_axis(
        control_socket.inputs,
        "drive_y",
        callback=lambda v: asyncio.create_task(
            make_input_callback("drive_y", commanded_inputs)(v)
        ),
    )

    for mode in range(3):
        control_socket.inputs.register_input(
            f"drive_mode_{mode}",
            type_="event",
            callback=lambda m=mode: asyncio.create_task(make_drive_mode_event(torqueController, control_socket, m, commanded_inputs)) or asyncio.sleep(0) or True
        )

    control_socket.inputs.register_input(
        f"clear_errors",
        type_="event",
        callback=lambda m=mode: asyncio.create_task(error_clear_event(torqueController)) or asyncio.sleep(0) or True
    )

    control_socket.inputs.register_input(
        f"control_take",
        type_="event",
        callback=lambda m=mode: asyncio.create_task(control_change(True)) or asyncio.sleep(0) or True
    )

    control_socket.inputs.register_input(
        f"control_release",
        type_="event",
        callback=lambda m=mode: asyncio.create_task(control_change(False)) or asyncio.sleep(0) or True
    )

    schema.register_axis(
        control_socket.inputs,
        "drive_multiplier",
        callback=lambda v: asyncio.create_task(
            make_input_callback("drive_multiplier", commanded_inputs)(v)
        ),
    )

    # -------------------------
    # REGISTER OUTPUTS
    # -------------------------

    control_socket.outputs.register_output("drive_x")
    control_socket.outputs.register_output("drive_y")

    control_socket.outputs.register_output("gyro_p")
    control_socket.outputs.register_output("gyro_y")
    control_socket.outputs.register_output("gyro_r")

    control_socket.outputs.register_output("vel_fd")
    control_socket.outputs.register_output("vel_up")
    control_socket.outputs.register_output("vel_lr")

    control_socket.outputs.register_output("drive_mode")

    await control_socket.start()
    
    imu_driver = imu.IMUDriver(control_socket)
    await imu_driver.start()

    logger.info(f"Drive control running on ws://{ws_host}:{ws_port}")

    # -------------------------
    # TASKS
    # -------------------------

    tasks = [
        asyncio.create_task(
            control_loop(
                commanded_inputs,
                control_socket,
                torqueController,
                shutdown_event,
                status_interval,
            ),
            name="control_loop",
        ),
        asyncio.create_task(
            heartbeat_loop(shutdown_event, heartbeat_interval),
            name="heartbeat_loop",
        ),
    ]

    # -------------------------
    # WAIT FOR SHUTDOWN
    # -------------------------

    await shutdown_event.wait()

    Status.setLED(Status.LEDCOLOUR.SAFE)

    logger.info("Shutting down tasks...")

    for t in tasks:
        t.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    await control_socket.stop()
    await imu_driver.stop()

    logger.info("Shutdown complete")


# -------------------------
# ENTRYPOINT
# -------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=5001)
    parser.add_argument("--ws_name", type=str, default="drive_control")
    parser.add_argument("--status_interval", type=float, default=0.02)
    parser.add_argument("--heartbeat", type=float, default=5.0)

    args = parser.parse_args()

    asyncio.run(
        main(
            args.ws_host,
            args.ws_port,
            args.ws_name,
            args.status_interval,
            args.heartbeat,
        )
    )