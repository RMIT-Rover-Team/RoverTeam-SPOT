import asyncio
import argparse
import json
import logging

import zmq
import zmq.asyncio
import sharedlib.payloadControl.pyRover as pyRover

# Connect to the IMU
IMU_ID = 0x2
imuMaster = pyRover.PyRover("can0",1)

# Row 0: Pitch Yaw Roll
# Row 1:
IMU_DATA_MATRIX = {
    "gyro":{"p":0, "y":0, "r":0},
    "vel":{"x":0,"y":0,"z":0}
}


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
# ZMQ TELEMETRY
# -------------------------
async def receive_loop(sub_socket):
    """Continuously receive ZMQ messages."""
    while True:
        try:
            msg = await sub_socket.recv_string(flags=zmq.NOBLOCK)
            
        except zmq.Again:
            await asyncio.sleep(0.01)  # prevent CPU spin

async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)

# -------------------------
# Await Can Data locally from IMU
# -------------------------
async def awaitCANData():
    global IMU_DATA_MATRIX

    RowLookup = {0:"gyro", 1:"vel"}
    ColLookup = {
        "gyro":["p","y","r"],
        "vel":["x","y","z"]
    }

    while True:
        # Intervalled code here 

        #Receive a broadcast in format ({'from': 0, 'stream_id': 0, 'channel_id': 0}, 0.0)
        nextDP = imuMaster.BroadcastDataPoint()

        if nextDP[0]['from'] == IMU_ID:
            #Update
            Row = RowLookup[nextDP[0]['stream_id']]

            Col = ColLookup[Row][nextDP[0]['channel_id']]

            IMU_DATA_MATRIX[Row][Col] = nextDP[1]

            #print("Recv",Row,Col,nextDP[1])

        await asyncio.sleep(0.05)

# -------------------------
# Publish IMU to frontend
# -------------------------
async def publishIMU():
    while True:
        msg = json.dumps({"type": "imu_data", "data": IMU_DATA_MATRIX})
        
        print(f"JSON {msg}")  # send data over to pdb
        await asyncio.sleep(0.1)


# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str):
    # Setup ZMQ
    ctx = zmq.asyncio.Context()
    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # Required tasks
    receive_task = asyncio.create_task(receive_loop(sub_socket))
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))

    # Extra tasks
    imucan_task = asyncio.create_task(awaitCANData())
    imufwd_task = asyncio.create_task(publishIMU())

    try:
        await asyncio.gather(
            # Required tasks
            receive_task,
            heartbeat_task,
            
            # Extra tasks
            imucan_task,
            imufwd_task
        )
    except asyncio.CancelledError:
        logging.info("Shutdown received, cancelling tasks")
    finally:
        # Required tasks
        receive_task.cancel()
        heartbeat_task.cancel()

        # Extra tasks
        webrtc_task.cancel()

        # propagate cancellation
        await asyncio.sleep(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=float, default=1.0, help="Heartbeat interval in seconds")
    parser.add_argument("--sub_url", type=str, default="tcp://127.0.0.1:5555", help="ZMQ SUB socket URL")
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.sub_url))