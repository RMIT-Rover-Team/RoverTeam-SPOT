import asyncio
import argparse
import json
import logging
import time
import math

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
    1: ODrive(1, bus, inverted=True),
    2: ODrive(2, bus),
    3: ODrive(3, bus, inverted=True),
    4: ODrive(4, bus),
}

# Control state
control_active = False

# -------------------------
# Heartbeat
# -------------------------

async def heartbeat_loop(interval: float):
    while True:
        # Could be used for simple logging/debug
        print("HEARTBEAT")
        await asyncio.sleep(interval)

def apply_control_curve(value: float, max_output: float = 50.0, steepness: float = 3.0) -> float:
    """
    Apply a curve to joystick input.
    - value: joystick input [0..1]
    - max_output: maximum speed/torque
    - steepness: higher = steeper at start, flatter at top
    """
    # Clamp input just in case
    value = max(0.0, min(1.0, value))

    # Sigmoid-like curve: y = x / (x + (1-x) * exp(-k*x))
    # simpler smoothstep variant: y = x^n / (x^n + (1-x)^n)
    n = steepness
    curved = (value**n) / (value**n + (1-value)**n) if value > 0 else 0.0

    return curved * max_output

# -------------------------
# Gamepad Handlers
# -------------------------

async def handle_gamepad_message(msg: dict, receiver):
    # Arm ODrives on first control message
    if "control_active" in msg:
        if receiver.control_active:
            for od in odrives.values():
                if not od.is_armed:
                    od.arm()

        if not receiver.control_active:
            for od in odrives.values():
                if od.is_armed:
                    od.disarm()
    elif "buttons" in msg and "axes" in msg:
        axes = msg["axes"]
        buttons = msg["buttons"]

        handle_button_batch(buttons, axes)
    else:
        logger.warning("unknown gamepad message: %s", msg)

def handle_button_batch(buttons, axes):
    rearm_button = buttons[0] if len(buttons) > 0 else 0.0
    max_speed = 200
    DEADZONE = 0.05

    x = axes[2] if len(axes) > 2 else 0.0
    y = axes[3] if len(axes) > 3 else 0.0

    # Apply deadzone
    x = 0.0 if abs(x) < DEADZONE else x
    y = 0.0 if abs(y) < DEADZONE else -y

    # Rotate by 45°
    cos45 = math.cos(math.pi / 4)
    sin45 = math.sin(math.pi / 4)

    left_speed = (y * cos45 + x * sin45) * max_speed
    right_speed = (y * cos45 - x * sin45) * max_speed

    # Optional: clamp speeds
    left_speed = max(-max_speed, min(max_speed, left_speed))
    right_speed = max(-max_speed, min(max_speed, right_speed))

    # Apply to motors
    for od in odrives.values():
        if rearm_button > 0 and not od.is_armed:
            od.arm()
        if od.is_armed:
            if od.node_id in (1, 2):
                od.set_velocity(left_speed)
            else:
                od.set_velocity(right_speed)

# -------------------------
# Telemetry loop
# -------------------------
async def telemetry_loop(interval: float, receiver):
    HEARTBEAT_GRACE_PERIOD = interval * 3 # can skip 3 heartbeats
    while True:
        # Collect drive status directly from each ODrive object
        now = time.time()
        data = {
            node_id: {
                "state": od.state,
                "error_code": od.error_code,
                "error_string": od.error_string,
                "traj_done": od.traj_done,
                "last_seen": od.last_heartbeat_time,
                "connected": (od.last_heartbeat_time is not None) and
                                (now - od.last_heartbeat_time <= HEARTBEAT_GRACE_PERIOD),
                "encoder_position": od.encoder_position,
                "encoder_velocity": od.encoder_velocity,
                "last_encoder": od.last_encoder_time,
            }
            for node_id, od in odrives.items()
        }

        # Send/print JSON telemetry
        print(f"JSON {json.dumps({'type': 'drive', 'data': data})}")
        await asyncio.sleep(interval)

# -------------------------
# MAIN
# -------------------------

async def main(heartbeat_interval: float, status_int: float, ws_host: str, ws_port: int):
    receiver = Receiver(lambda msg: handle_gamepad_message(msg, receiver))
    gamepad_server = GamepadServer(ws_host, ws_port, receiver, odrives)

    # Start server
    await gamepad_server.start()

    # Only keep heartbeat and slow telemetry as fallback
    tasks = [
        asyncio.create_task(heartbeat_loop(heartbeat_interval)),
        asyncio.create_task(telemetry_loop(status_int, receiver))
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