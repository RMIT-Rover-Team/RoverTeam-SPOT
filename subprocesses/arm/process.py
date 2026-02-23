import asyncio
import argparse
import json
import logging
import time
from typing import List

from sharedlib.controlsocket.controlsocket import ControlSocket
from sharedlib.controlsocket import schema

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
# ARM STATE
# -------------------------
NUM_AXES = 6
AXIS_NAMES = ["axis_x", "axis_y", "axis_z", "axis_roll", "axis_pitch", "axis_yaw"]

axis_targets: List[float] = [0.0] * NUM_AXES    # raw velocity commands
axis_positions: List[float] = [0.0] * NUM_AXES  # simulated positions
axis_last_update: List[float] = [None] * NUM_AXES

# -------------------------
# CALLBACK FOR AXES
# -------------------------
async def handle_axis(axis_id: int, value: float):
    axis_targets[axis_id] = value
    axis_last_update[axis_id] = time.time()
    logger.debug(f"Axis {AXIS_NAMES[axis_id]} set to {value}")

# -------------------------
# TELEMETRY LOOP
# -------------------------
async def telemetry_loop(control_socket: ControlSocket, interval: float):
    while True:
        for i, name in enumerate(AXIS_NAMES):
            # Update position instantly based on raw input
            axis_positions[i] += axis_targets[i] * interval
            await control_socket.outputs.update_output(name, axis_positions[i])
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
async def main(ws_host: str, ws_port: int, ws_name: str, heartbeat: float, status_interval: float):
    control_socket = ControlSocket(ws_host, ws_port, ws_name, allow_multiple_clients=False)
    
    # Register axes with ControlSocket
    for i, name in enumerate(AXIS_NAMES):
        schema.register_axis(
            control_socket.inputs,
            name,
            callback=lambda v, axis=i: handle_axis(axis, v)
        )
        control_socket.outputs.register_output(name)

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

    asyncio.run(main(args.ws_host, args.ws_port, args.ws_name, args.heartbeat, args.status_interval))