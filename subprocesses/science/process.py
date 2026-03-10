import argparse
import asyncio
import json
import logging
import signal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from sharedlib.canbus.client import CANClient
from sharedlib.models import BoardID
from sharedlib.payloadControl import pyRover
from subprocesses.pdb.telemetry.manager import PDBManager


# logger.log(25, msg) (SUCCESS)
# -------------------------
# CONFIG
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {"level": record.levelname, "msg": record.getMessage()}
        print(json.dumps(log_obj), flush=True)


logger = logging.getLogger("pdb")
logger.setLevel(logging.INFO)
logger.addHandler(JsonHandler())

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (React app, etc.)
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],  # Allows all headers
)

pdb: PDBManager
shutdown_event = asyncio.Event()

polling_intervals = {"websocket": 1.0, "can": 1.0}

async def heartbeat_loop(interval: float):
    """
    Sends a heartbeat to the main supervisor to say the subprocess is alive.
        interval -- interval in seconds
    """
    while not shutdown_event.is_set():
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# PDB Loops
# -------------------------
async def pdb_websocket_loop(pdb: PDBManager, interval: float = 1.0) -> None:
    """
    Takes the state of PDBManager and sends it through the telemetry websocket. The topic of the pdb_telemetry_loop is pdb_data.
        pdb -- The PDB manager that receives, sends and stores pdb data
        interval -- interval in seconds
    """
    try:
        polling_intervals["websocket"] = interval
        while not shutdown_event.is_set():
            # Get the data
            data = pdb.get_pending_data()
            if data:
                msg = json.dumps({"type": "pdb_data", "data": data})
                print(f"JSON {msg}")  # send data over to pdb

            await asyncio.sleep(polling_intervals["websocket"])
    except Exception as e:
        logger.error(f"Sending PDB Telemetry Data ran into an error: {e}")
        request_shutdown()  # request shutdown to restart


async def pdb_can_loop(pdb: PDBManager, interval: float = 1.0) -> None:
    """
    Sends a request for PDB data from pdb manager to update it.
        pdb -- The PDB manager that receives, sends and stores pdb data
        interval -- interval in seconds
    """
    try:
        logger.info(f"PDB: Starting sequenced polling (step: {interval}s)")
        polling_intervals["can"] = interval
        while not shutdown_event.is_set():
            for board in BoardID:
                await pdb.request_board_data(board)
                await asyncio.sleep(polling_intervals["can"])

                logger.info(f"Can interval {polling_intervals['can']}")
                if shutdown_event.is_set():
                    break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Sequenced Polling Loop error: {e}")
        request_shutdown()


@app.get("/ping")
async def ping():
    """
    Pings frontend
    """
    return PlainTextResponse("pdb")


@app.post("/switch1/channel/{channel}/{enable}")
async def toggle_switch(channel: int, enable: int):
    # Validation
    if not (0 <= channel <= 7):
        raise HTTPException(status_code=400, detail="Channel does not exist")
    if enable not in [0, 1]:
        raise HTTPException(status_code=400, detail="Enable must be 0 or 1")

    is_on = True if enable == 1 else False

    await pdb.toggle_channel(BoardID.SWITCH, channel, is_on)

    logger.info(f"COMMAND: Switch Board | Channel: {channel} | State: {is_on}")

    return {"message": f"Switch channel {'enabled' if is_on else 'disabled'}"}


@app.post("/buck1/channel/{channel}/{enable}")
async def toggle_buck1(channel: int, enable: int):
    if not (0 <= channel <= 4):
        raise HTTPException(status_code=400, detail="Channel does not exist")
    if enable not in [0, 1]:
        raise HTTPException(status_code=400, detail="Enable must be 0 or 1")

    is_on = True if enable == 1 else False

    await pdb.toggle_channel(BoardID.BUCK1, channel, is_on)
    return {"message": f"Buck 1 channel {'enabled' if enable else 'disabled'}"}


@app.post("/buck2/channel/{channel}/{enable}")
async def toggle_buck2(channel: int, enable: int):
    if not (0 <= channel <= 4):
        raise HTTPException(status_code=400, detail="Channel does not exist")

    is_on = True if enable == 1 else False

    await pdb.toggle_channel(BoardID.BUCK2, channel, is_on)
    return {"message": "Buck 2 updated"}


@app.post("/bms/estop")
async def estop_bms():
    await pdb.cut_power(1)
    await pdb.cut_power(2)
    await pdb.cut_power(3)


@app.post("/can/polling/{interval}")
async def change_can_interval(interval: float):
    # Validation
    if interval < 0:
        raise HTTPException(status_code=400, detail="Interval must be greater than 0")

    polling_intervals["can"] = interval

    logger.info(f"Changed can interval to {polling_intervals['can']}")

    return {"message": f"CAN polling rate set to {interval}"}


@app.post("/websocket/polling/{interval}")
async def change_websocket_interval(interval: float):
    # Validation
    if interval < 0:
        raise HTTPException(status_code=400, detail="Interval must be greater than 0")

    polling_intervals["websocket"] = interval

    logger.info(f"Changed can interval to {polling_intervals['websocket']}")

    return {"message": f"Websocket polling rate set to {interval}"}


# -------------------------
# CLEAN SHUTDOWN
# -------------------------
def request_shutdown():
    logger.info("Shutdown signal received")
    shutdown_event.set()


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
    global pdb

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # -------------------------
    # CAN setup
    # -------------------------
    can_client = CANClient()
    await can_client.start()

    pdb_master = pyRover.PyRover("can0", 16)

    pdb = PDBManager(can_client, pdb_master, logger)
    pdb.register_all()

    # -------------------------
    # Websocket
    # -------------------------
    # Required tasks
    config = uvicorn.Config(app, host=args.ws_host, port=args.ws_port, log_level="info")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    global polling_intervals
    polling_intervals = {"websocket": 1.0, "can": 1.0}

    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))
    pdb_websocket_task = asyncio.create_task(
        pdb_websocket_loop(pdb, interval=polling_intervals["websocket"])
    )
    pdb_can_task = asyncio.create_task(
        pdb_can_loop(pdb, interval=polling_intervals["can"])
    )

    # Wait for shutdown...
    await shutdown_event.wait()

    # Cleanup
    await server_task
    heartbeat_task.cancel()
    pdb_websocket_task.cancel()
    pdb_can_task.cancel()

    await asyncio.sleep(0)
    await can_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=5000)
    parser.add_argument("--ws_name", type=str, default="pdb_telemetry")
    parser.add_argument("--status_interval", type=float, default=0.02)
    parser.add_argument("--heartbeat", type=float, default=2.0)

    args = parser.parse_args()
    # vcan0 181#7200423700000000
    asyncio.run(
        main(
            args.ws_host,
            args.ws_port,
            args.ws_name,
            args.status_interval,
            args.heartbeat,
        )
    )
