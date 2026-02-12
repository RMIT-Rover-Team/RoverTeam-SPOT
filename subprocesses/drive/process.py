import asyncio
import argparse
import json
import logging

from gamepad_ws.receiver import Receiver
from gamepad_ws.server import GamepadServer
from gamepad_ws.cors import cors_middleware

from canbus.canbus import CANBus
from canbus.ODrive import ODrive

# -------------------------
# CONFIG
# -------------------------

class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {"level": record.levelname, "msg": record.getMessage()}
        print(json.dumps(log_obj), flush=True)


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(JsonHandler())

# -------------------------
# CAN + ODrive setup
# -------------------------

bus = CANBus("can0")

odrives = {
    1: ODrive(1, bus, inverted = True),
    2: ODrive(2, bus),
    3: ODrive(3, bus, inverted = True),
    4: ODrive(4, bus),
}

control_active = False

# -------------------------
# Heartbeat
# -------------------------

async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)

# -------------------------
# Gamepad Handlers
# -------------------------

async def handle_gamepad_message(msg: dict):
    global control_active

    # Arm ODrives on first control message
    if not control_active:
        logger.info("Controller active — arming ODrives")
        for od in odrives.values():
            od.arm()
        control_active = True

    if "buttons" in msg and "axes" in msg:
        buttons = msg["buttons"]
        axes = msg["axes"]

        for i, value in enumerate(axes):
            handle_axis({"id": i, "value": value})

        handle_button_batch(buttons)
    else:
        logger.warning("unknown gamepad message: %s", msg)


def handle_axis(data):
    axis_id = data["id"]
    value = data["value"]
    # TODO: steering, camera pan, etc

def handle_button_batch(buttons):
    forward = buttons[7] if len(buttons) > 7 else 0.0
    reverse = buttons[6] if len(buttons) > 6 else 0.0

    max_speed = 50
    deadzone = 0.05

    if forward < deadzone:
        forward = 0.0
    if reverse < deadzone:
        reverse = 0.0

    # SAFETY: both pressed or neither pressed → stop
    if (forward > 0 and reverse > 0) or (forward == 0 and reverse == 0):
        speed = 0.0
    elif forward > 0:
        speed = forward * max_speed
    else:  # reverse > 0
        speed = -reverse * max_speed

    # Drivetrain inversion
    odrives[1].set_velocity(speed)
    odrives[2].set_velocity(speed)
    odrives[3].set_velocity(speed)
    odrives[4].set_velocity(speed)


# -------------------------
# Telemetry loop (feedback from ODrives)
# ------------------------

async def telemetry_loop(interval: float = 1.0):
    while True:
        data = {}
        for node_id, od in odrives.items():
            # call heartbeat listener
            od.listen_for_heartbeat(timeout=0.01)

            data[node_id] = {
                "state": od.state,
                "error_code": od.error_code,
                "error_string": od.error_string,
                "traj_done": od.traj_done,
                "last_seen": od.last_heartbeat_time
            }

        print(json.dumps({"type": "drive", "data": data}))
        await asyncio.sleep(interval)


# -------------------------
# MAIN
# -------------------------

async def main(heartbeat_interval: float, status_int: float, ws_host: str, ws_port: int):
    receiver = Receiver(handle_gamepad_message)
    gamepad_server = GamepadServer(ws_host, ws_port, receiver)

    await gamepad_server.start()

    tasks = [
        asyncio.create_task(heartbeat_loop(heartbeat_interval)),
        asyncio.create_task(telemetry_loop(status_int))
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutdown received")
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.sleep(0)
        await gamepad_server.stop()

# -------------------------
# ENTRYPOINT
# -------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=float, default=1.0)
    parser.add_argument("--odrive_status_interval", type=float, default=1.0)
    parser.add_argument("--sub_url", type=str)
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=8765)
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.odrive_status_interval, args.ws_host, args.ws_port))