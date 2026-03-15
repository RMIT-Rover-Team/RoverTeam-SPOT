import argparse
import asyncio
import json
import logging
import signal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from sharedlib.models import ScienceID
from sharedlib.payloadControl import pyRover
from subprocesses.science.manager import ScienceManager

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

science: ScienceManager
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
# Science Loops
# -------------------------
async def science_websocket_loop(
    science: ScienceManager, interval: float = 1.0
) -> None:
    """
    Takes the state of science manager and sends it through the telemetry websocket. The topic of the science_telemetry_loop is science_data.
        science -- The science manager that receives, sends and stores pdb data
        interval -- interval in seconds
    """
    try:
        polling_intervals["websocket"] = interval
        while not shutdown_event.is_set():
            # Get the data
            data = science.get_telemetry_data()
            if data:
                msg = json.dumps({"type": "science_data", "data": data})
                print(f"JSON {msg}")  # send data over to science

            await asyncio.sleep(polling_intervals["websocket"])
    except Exception as e:
        logger.error(f"Sending Science Telemetry Data ran into an error: {e}")
        request_shutdown()  # request shutdown to restart


async def science_can_loop(science: ScienceManager, interval: float = 1.0) -> None:
    """
    Sends a request for science data from science manager to update it.
        science -- The science manager that receives, sends and stores pdb data
        interval -- interval in seconds
    """
    await asyncio.sleep(0.1)
    stepper_ids = [ScienceID.AUGER, ScienceID.MICROSCOPE, ScienceID.MICROSCOPE_SWIVEL]
    try:
        while not shutdown_event.is_set():
            await science.refresh_drill_telemetry()
            [await science.refresh_stepper_telemetry(s_id) for s_id in stepper_ids]
    
            await asyncio.sleep(polling_intervals["can"])
    except Exception as e:
        logger.error(f"Sequenced Polling Loop error: {e}")
        request_shutdown()


@app.get("/ping")
async def ping():
    """
    Pings frontend
    """
    return PlainTextResponse("science")


@app.post("/science/estop")
async def estop():
    science.estop()


@app.post("/drill/speed/{speed}")
async def set_drill_speed(speed: int):
    await science.set_drill_speed(speed)

    logger.info(f"COMMAND: Science Drill speed | Speed: {speed}")
    return {"message": f"Set drill speed to {speed}"}


@app.post("/steppers/{motor_id}/{steps}")
async def set_stepper_steps(motor_id: int, steps: int):
    if motor_id > 3 or motor_id == 0:
        raise HTTPException(status_code=400, detail="Motor id is invalid")

    await science.set_stepper_steps(motor_id, steps)
    return {"message": f"Set motor {motor_id} to step {steps} times."}


@app.post("/heatpad/{toggle}")
async def set_heatpad_toggle(toggle: int):
    heatpad_status = True if toggle == 1 else False

    
    await science.set_heatpad_toggle(heatpad_status)

@app.post("/science/can/polling/{interval}")
async def change_can_interval(interval: float):
    # Validation
    if interval < 0:
        raise HTTPException(status_code=400, detail="Interval must be greater than 0")

    polling_intervals["can"] = interval

    logger.info(f"Changed can interval to {polling_intervals['can']}")

    return {"message": f"CAN polling rate set to {interval}"}


@app.post("/science/websocket/polling/{interval}")
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
    global science

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    # -------------------------
    # CAN setup
    # -------------------------
    science_master = pyRover.PyRover("can0", 0)
    science = ScienceManager(science_master, logger)

    # -------------------------
    # Websocket
    # -------------------------
    # Required tasks
    config = uvicorn.Config(app, host=args.ws_host, port=args.ws_port, log_level="info")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    global polling_intervals
    polling_intervals = {"websocket": 1.0, "can": 2.0}

    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))
    science_websocket_task = asyncio.create_task(
        science_websocket_loop(science, interval=polling_intervals["websocket"])
    )
    science_can_task = asyncio.create_task(
        science_can_loop(science, interval=polling_intervals["can"])
    )

    # Wait for shutdown...
    await shutdown_event.wait()
    await server_task


    # Cleanup
    heartbeat_task.cancel()
    science_websocket_task.cancel()
    science_can_task.cancel()

    await asyncio.sleep(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws_host", type=str, default="0.0.0.0")
    parser.add_argument("--ws_port", type=int, default=5003)
    parser.add_argument("--ws_name", type=str, default="science_telemetry")
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
