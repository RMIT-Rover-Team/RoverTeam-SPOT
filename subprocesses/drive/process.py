import asyncio
import argparse
import json
import logging
import signal

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema

import driveStackBinaries.torque as torque

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

        drive_l, drive_r = calc_drive(commanded_inputs["drive_x"], commanded_inputs["drive_y"])

        torqueController.set_speed()

        if drive_mode == 0:
            # Unlocked differential
            torqueController.set_mode(torque.UNLOCKED_VELOCITY)

            pass

        elif drive_mode == 1:
            # Locked differential
            torqueController.set_mode(torque.LOCKED_VELOCITY)

            pass

        elif drive_mode == 2:
            # Direct torque mode (dangerous!)
            torqueController.set_mode(torque.UNLOCKED_TORQUE)

            pass

        else:
            logger.warning(f"Unknown drive_mode: {drive_mode}")

        await asyncio.sleep(interval)


# -------------------------
# HEARTBEAT
# -------------------------

async def heartbeat_loop(shutdown_event, interval):
    while not shutdown_event.is_set():
        logger.info("HEARTBEAT")
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
):

    # -------------------------
    # INPUT STATE
    # -------------------------

    torqueController = torque.TorqueHandler("can0")
    torqueController.enable()

    commanded_inputs = {
        "drive_x": 0.0,
        "drive_y": 0.0,
        "drive_mode": 0
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

    schema.register_axis(
        control_socket.inputs,
        "drive_mode",
        callback=lambda v: asyncio.create_task(
            make_input_callback("drive_mode", commanded_inputs)(v)
        ),
    )

    # -------------------------
    # REGISTER OUTPUTS
    # -------------------------

    control_socket.outputs.register_output("drive_x")
    control_socket.outputs.register_output("drive_y")

    await control_socket.start()

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

    logger.info("Shutting down tasks...")

    for t in tasks:
        t.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    await control_socket.stop()

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