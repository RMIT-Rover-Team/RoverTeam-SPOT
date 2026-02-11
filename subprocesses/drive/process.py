import asyncio
import argparse
import json
import logging

from gamepad_ws.receiver import Receiver
from gamepad_ws.server import GamepadServer
from gamepad_ws.cors import cors_middleware

from canbus.ODrive import set_velocity, startup

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
    if "buttons" in msg and "axes" in msg:
        # New frontend format: batch buttons and axes
        buttons = msg["buttons"]
        axes = msg["axes"]

        for i, value in enumerate(axes):
            handle_axis({"id": i, "value": value})

        for i, pressed in enumerate(buttons):
            handle_button({"id": i, "pressed": pressed > 0, "analog": pressed})
    else:
        logger.warning("unknown gamepad message: %s", msg)

def handle_axis(data):
    axis_id = data["id"]
    value = data["value"]
    # logger.warning("Axis %d → %.3f", axis_id, value)
    # TODO: Forward to rover control loop


def handle_button(data):
    button_id = data["id"]
    pressed = data["pressed"]
    
    if button_id == 7:
        # assume ODrive.set_speed takes a float -1.0..1.0
        # scale trigger (0..1) to speed (0..max_speed)
        analog = data.get("analog", 0)
        max_speed = 200  # example units
        speed = analog * max_speed
        set_velocity(4, speed)

startup(4)


# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, ws_host: str, ws_port: int):
    # Setup Gamepad receiver/server
    receiver = Receiver(handle_gamepad_message)
    gamepad_server = GamepadServer(ws_host, ws_port, receiver)
    await gamepad_server.start()

    # Create tasks
    tasks = [
        asyncio.create_task(heartbeat_loop(heartbeat_interval))
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutdown received, cancelling tasks")
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
    parser.add_argument("--heartbeat", type=float, default=1.0, help="Heartbeat interval in seconds")
    parser.add_argument("--sub_url", type=str)
    parser.add_argument("--ws_host", type=str, default="0.0.0.0", help="WebSocket host")
    parser.add_argument("--ws_port", type=int, default=8765, help="WebSocket port")
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.ws_host, args.ws_port))