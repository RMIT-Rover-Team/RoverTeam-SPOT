import asyncio
import argparse
import json
import logging
import time

from gamepad_ws.receiver import Receiver
from gamepad_ws.server import GamepadServer

#Import the universal payload control layer
import payloadControlBinaries.pyRover as pyRover


PayloadID = 0xB

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



#Initialise the master
payloadMaster = pyRover.PyRover("can0",1)

# -------------------------
# Helpers
# -------------------------


# -------------------------
# Gamepad Handlers
# -------------------------

async def handle_gamepad_message(msg: dict, receiver):

    if "buttons" in msg and "axes" in msg:
        axes = msg["axes"]
        handle_axes(axes)
    else:
        logger.warning("unknown gamepad message: %s", msg)


def handle_axes(axes):
    axis2 = axes[2] if len(axes) > 2 else 0.0
    axis3 = axes[3] if len(axes) > 3 else 0.0

    Mapped2 = axis2 * 120
    Mapped3 = axis3 * 120

    if (Mapped2 > 0.1):
        pyRover.SetMotorSpeed(PayloadID,0,Mapped2)

    if (Mapped3 > 0.1):
        pyRover.SetMotorSpeed(PayloadID,1,Mapped3)


# -------------------------
# Telemetry Loop
# -------------------------

async def telemetry_loop(interval: float):
    while True:
        now = time.time()

        data = {
            "payloadOnline":payloadMaster.ping(PayloadID)
        }

        print(f"JSON {json.dumps({'type': 'excavator', 'data': data})}")
        await asyncio.sleep(interval)

async def heartbeat_loop(interval: float):
    while True:
        # Could be used for simple logging/debug
        print("HEARTBEAT")
        await asyncio.sleep(interval)

# -------------------------
# MAIN
# -------------------------

async def main(heartbeat: float, sub_url: str, status_interval: float, ws_host: str, ws_port: int):

    receiver = Receiver(lambda msg: handle_gamepad_message(msg, receiver))
    gamepad_server = GamepadServer(ws_host, ws_port, receiver, sender_agents={})

    await gamepad_server.start()

    tasks = [
        asyncio.create_task(heartbeat_loop(heartbeat)),
        asyncio.create_task(telemetry_loop(status_interval))
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
    parser.add_argument("--heartbeat", type=float, default=10)
    parser.add_argument("--status_interval", type=float, default=0.2)
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--sub_url", type=str)
    parser.add_argument("--ws_port", type=int, default=8766)
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.sub_url, args.status_interval, args.ws_host, args.ws_port))