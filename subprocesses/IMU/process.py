import asyncio
import argparse
import json
import logging
import platform
import math
import time

import zmq
import zmq.asyncio

# -------------------------
# ENVIRONMENT DETECTION
# -------------------------
IS_WINDOWS = platform.system() == "Windows"

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
# IMU STATE
# -------------------------
IMU_ID = 0x2

IMU_DATA_MATRIX = {
    "gyro": {"p": 0, "y": 0, "r": 0},
    "vel": {"fd": 0, "up": 0, "lr": 0}
}

SIMULATED = False

# -------------------------
# ZMQ TELEMETRY
# -------------------------
async def receive_loop(sub_socket):
    """Continuously receive ZMQ messages."""
    while True:
        try:
            _ = await sub_socket.recv_string(flags=zmq.NOBLOCK)
        except zmq.Again:
            await asyncio.sleep(0.01)


async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# REAL IMU (CAN)
# -------------------------
async def awaitCANData(imuMaster):
    global IMU_DATA_MATRIX

    RowLookup = {0: "gyro", 1: "vel"}

    ColLookup = {
        "gyro": ["p", "y", "r"],
        "vel": ["fd", "up", "lr"]
    }

    while True:

        # Receive broadcast datapoint
        # Format: ({'from': 0, 'stream_id': 0, 'channel_id': 0}, value)
        nextDP = imuMaster.BroadcastDataPoint()

        if nextDP[0]['from'] == IMU_ID:

            row = RowLookup[nextDP[0]['stream_id']]
            col = ColLookup[row][nextDP[0]['channel_id']]

            IMU_DATA_MATRIX[row][col] = nextDP[1]

            IMU_DATA_MATRIX["simulated"] = True

        await asyncio.sleep(0.05)


# -------------------------
# SIMULATED IMU
# -------------------------
async def fakeIMUData():
    global IMU_DATA_MATRIX

    start = time.time()

    while True:

        t = time.time() - start

        IMU_DATA_MATRIX["simulated"] = True

        # smooth fake rotations
        IMU_DATA_MATRIX["gyro"]["p"] = math.sin(t) * 30
        IMU_DATA_MATRIX["gyro"]["y"] = math.cos(t * 0.7) * 45
        IMU_DATA_MATRIX["gyro"]["r"] = math.sin(t * 0.5) * 20

        # fake velocity drift
        IMU_DATA_MATRIX["vel"]["fd"] = math.sin(t * 0.4)
        IMU_DATA_MATRIX["vel"]["up"] = math.cos(t * 0.6)
        IMU_DATA_MATRIX["vel"]["lr"] = math.sin(t * 0.9)

        await asyncio.sleep(0.05)


# -------------------------
# PUBLISH IMU
# -------------------------
async def publishIMU():
    while True:

        msg = json.dumps({
            "type": "imu_data",
            "data": IMU_DATA_MATRIX
        })

        print(f"JSON {msg}")

        await asyncio.sleep(0.1)


# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str, force_sim: bool):

    global SIMULATED

    # -------------------------
    # Determine simulation mode
    # -------------------------
    if force_sim or IS_WINDOWS:
        SIMULATED = True
    else:
        SIMULATED = False

    # -------------------------
    # Setup ZMQ
    # -------------------------
    ctx = zmq.asyncio.Context()

    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    receive_task = asyncio.create_task(receive_loop(sub_socket))
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))

    # -------------------------
    # IMU mode
    # -------------------------
    if SIMULATED:

        logging.info("Running with SIMULATED IMU data")

        imu_task = asyncio.create_task(fakeIMUData())

    else:

        logging.info("Running with REAL CAN IMU")

        import sharedlib.payloadControl.pyRover as pyRover

        imuMaster = pyRover.PyRover("can0", 1)

        imu_task = asyncio.create_task(awaitCANData(imuMaster))

    imufwd_task = asyncio.create_task(publishIMU())

    try:

        await asyncio.gather(
            receive_task,
            heartbeat_task,
            imu_task,
            imufwd_task
        )

    except asyncio.CancelledError:

        logging.info("Shutdown received, cancelling tasks")

    finally:

        receive_task.cancel()
        heartbeat_task.cancel()
        imu_task.cancel()
        imufwd_task.cancel()

        await asyncio.sleep(0)


# -------------------------
# ENTRY
# -------------------------
if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--heartbeat",
        type=float,
        default=1.0,
        help="Heartbeat interval in seconds"
    )

    parser.add_argument(
        "--sub_url",
        type=str,
        default="tcp://127.0.0.1:5555",
        help="ZMQ SUB socket URL"
    )

    parser.add_argument(
        "--sim",
        action="store_true",
        help="Force simulated IMU even on Linux"
    )

    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.sub_url, args.sim))