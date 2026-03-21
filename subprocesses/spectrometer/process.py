import argparse
import asyncio
import json
import logging
import signal
import sys
import serial
import serial.tools.list_ports

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

# -------------------------
# CONFIG
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {"level": record.levelname, "msg": record.getMessage()}
        print(json.dumps(log_obj), flush=True)

logger = logging.getLogger("spectrometer")
logger.setLevel(logging.INFO)
logger.addHandler(JsonHandler())

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

shutdown_event = asyncio.Event()

async def heartbeat_loop(interval: float):
    while not shutdown_event.is_set():
        print("HEARTBEAT", flush=True)
        await asyncio.sleep(interval)

@app.get("/ping")
async def ping():
    return PlainTextResponse("spectrometer")

def request_shutdown():
    logger.info("Shutdown signal received")
    shutdown_event.set()

async def serial_read_loop(port: str, baudrate: int):
    try:
        ser = serial.Serial(port, baudrate, timeout=0.1)
        logger.info(f"Connected to spectrometer on {port} at {baudrate} baud.")
    except Exception as e:
        logger.error(f"Failed to connect to spectrometer on {port}: {e}")
        return
    
    while not shutdown_event.is_set():
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    # Line should be comma separated values
                    try:
                        values = [int(v) for v in line.split(',') if v.strip()]
                        if len(values) > 0:
                            msg = json.dumps({"type": "spectrometer_data", "data": {"channels": values}})
                            print(f"JSON {msg}", flush=True)
                    except ValueError:
                        pass
            else:
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            break
            
    if ser and ser.is_open:
        ser.close()

async def main(
    port: str,
    baudrate: int,
    ws_port: int,
    heartbeat_interval: float,
):
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    config = uvicorn.Config(app, host="0.0.0.0", port=ws_port, log_level="warning")
    server = uvicorn.Server(config)
    
    server_task = asyncio.create_task(server.serve())
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))
    serial_task = asyncio.create_task(serial_read_loop(port, baudrate))

    await shutdown_event.wait()
    
    server_task.cancel()
    heartbeat_task.cancel()
    serial_task.cancel()
    await asyncio.sleep(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=str, default="COM8")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--ws_port", type=int, default=5004)
    parser.add_argument("--heartbeat", type=float, default=2.0)

    args = parser.parse_args()
    asyncio.run(
        main(
            args.port,
            args.baudrate,
            args.ws_port,
            args.heartbeat,
        )
    )
