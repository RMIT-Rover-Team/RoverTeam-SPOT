import asyncio
import argparse
import json
import logging

from gamepad_ws.receiver import Receiver
from gamepad_ws.server import GamepadWSServer

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
    msg_type = msg.get("type")
    data = msg.get("data")

    match msg_type:
        case "axis":
            handle_axis(data)
        case "button":
            handle_button(data)
        case _:
            logger.warning("Unknown gamepad message: %s", msg)

def handle_axis(data):
    axis_id = data["id"]
    value = data["value"]
    logger.debug("Axis %d → %.3f", axis_id, value)
    # TODO: Forward to rover control loop

def handle_button(data):
    button_id = data["id"]
    pressed = data["pressed"]
    logger.debug("Button %d → %s", button_id, pressed)
    # TODO: Toggle modes, arm/disarm, etc.

# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, ws_host: str, ws_port: int):
    # Setup Gamepad receiver/server
    receiver = Receiver(handle_gamepad_message)
    gamepad_server = GamepadWSServer(ws_host, ws_port, receiver)
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
    parser.add_argument("--ws_host", type=str, default="0.0.0.0", help="WebSocket host")
    parser.add_argument("--ws_port", type=int, default=8765, help="WebSocket port")
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.ws_host, args.ws_port))