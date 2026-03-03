import argparse
import asyncio
import json
import logging
import signal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from models import BoardID

from sharedlib.canbus.client import CANClient
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

pdb: PDBManager | None = None
shutdown_event = asyncio.Event()


async def heartbeat_loop(interval: float):
    while not shutdown_event.is_set():
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# PDB Loops
# -------------------------
async def pdb_telemetry_loop(pdb: PDBManager, interval: float):
    try:
        while not shutdown_event.is_set():
            # Get the data
            data = pdb.get_snapshot()
            msg = json.dumps({"type": "pdb_data", "data": data})
            print(f"JSON {msg}")  # send data over to pdb
            await asyncio.sleep(interval)
    except Exception as e:
        logger.error(f"Sending PDB Telemetry Data ran into an error: {e}")
        request_shutdown()  # request shutdown to restart


@app.get("/ping")
async def ping():
    return PlainTextResponse("pdb")


@app.post("/switch1/channel/{channel}/{enable}")
async def toggle_switch(channel: int, enable: int):
    # Validation
    if not (0 <= channel <= 7):
        raise HTTPException(status_code=400, detail="Channel does not exist")
    if enable not in [0, 1]:
        raise HTTPException(status_code=400, detail="Enable must be 0 or 1")

    await pdb.toggle_channel(BoardID.SWITCH, channel, bool(enable))

    state = "enabled" if enable else "disabled"
    return {"message": f"Switch channel {state}"}


@app.post("/buck1/channel/{channel}/{enable}")
async def toggle_buck1(channel: int, enable: int):
    if not (0 <= channel <= 4):
        raise HTTPException(status_code=400, detail="Channel does not exist")
    if enable not in [0, 1]:
        raise HTTPException(status_code=400, detail="Enable must be 0 or 1")

    await pdb.toggle_channel(BoardID.BUCK1, channel, bool(enable))
    return {"message": f"Buck 1 channel {'enabled' if enable else 'disabled'}"}


@app.post("/buck2/channel/{channel}/{enable}")
async def toggle_buck2(channel: int, enable: int):
    if not (0 <= channel <= 4):
        raise HTTPException(status_code=400, detail="Channel does not exist")

    await pdb.toggle_channel(BoardID.BUCK2, channel, bool(enable))
    return {"message": "Buck 2 updated"}


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

    pdb = PDBManager(can_client, logger)
    pdb.register_all()

    # -------------------------
    # Websocket
    # -------------------------
    # Required tasks
    config = uvicorn.Config(app, host=args.ws_host, port=args.ws_port, log_level="info")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))
    pdb_task = asyncio.create_task(pdb_telemetry_loop(pdb, interval=1))

    # Wait for shutdown...
    await shutdown_event.wait()

    # Cleanup
    await server_task
    pdb_task.cancel()
    heartbeat_task.cancel()

    await asyncio.sleep(0)
    await can_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=8766)
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
