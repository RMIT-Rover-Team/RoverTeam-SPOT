import asyncio
import argparse
import json
import logging
import serial
import traceback

import zmq
import zmq.asyncio

# -------------------------
# CONFIG
# -------------------------
# NOTES
# MAX brightness value return from spectrometer will be
# from green 9V laser pointed directly
# returning 1530
# set that as 100% so not most values get 100%

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
            # Add ZMQ message handling here if needed
        except zmq.Again:
            await asyncio.sleep(0.01)  # prevent CPU spin

async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)

# -------------------------
# SERIAL COMMUNICATION
# -------------------------
def read_serial_line_blocking(ser: serial.Serial) -> str:
    """Read a line from the serial port, returning empty string on timeout."""
    if ser.in_waiting > 0:
        line = ser.readline()
        try:
            return line.decode('utf-8').strip()
        except UnicodeDecodeError:
            pass
    return ""

async def serial_loop(port: str, baudrate: int = 115200):
    """Continuously read from the spectrometer serial port."""
    try:
        # We will use a non-blocking timeout of 0, checking in_waiting manually
        ser = serial.Serial(port, baudrate, timeout=0)
        logger.info(f"Successfully opened serial port {port} at {baudrate} baud.")
    except Exception as e:
        logger.error(f"Failed to open serial port {port}: {e}")
        return

    while True:
        try:
            # We use to_thread to prevent any possible blocking in readline() 
            # if we switched to timeout>0, but with timeout=0 and in_waiting 
            # we can just read it directly here as well. Using to_thread is safer.
            line = await asyncio.to_thread(read_serial_line_blocking, ser)

            if line:
                # The Arduino outputs comma separated values, e.g., "val1,val2,...,val288,"
                if line.endswith(','):
                    line = line[:-1]
                
                parts = line.split(',')
                # Check if we got the expected number of channels (288) or valid integers
                try:
                    data = [int(x) for x in parts if x.strip()]
                    if data:
                        # Output via standard stdout JSON telemetry format
                        print(f"JSON {json.dumps({'type': 'spectrometer', 'data': data})}")
                        # logger.info(f"Spectrometer read OK — last 5 values: {data[-5:]}")
                except ValueError:
                    logger.debug(f"Could not parse line: {line}")
            else:
                await asyncio.sleep(0.01) # Avoid busy waiting if no data
                
        except serial.SerialException as e:
            logger.error(f"Serial exception: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected error in serial_loop: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(1) # Backoff on error

# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str, serial_port: str):
    # Setup ZMQ
    ctx = zmq.asyncio.Context()
    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # Required tasks
    receive_task = asyncio.create_task(receive_loop(sub_socket))
    heartbeat_task = asyncio.create_task(heartbeat_loop(heartbeat_interval))

    # Extra tasks
    spectrometer_task = asyncio.create_task(serial_loop(serial_port))

    try:
        await asyncio.gather(
            # Required tasks
            receive_task,
            heartbeat_task,
            
            # Extra tasks
            spectrometer_task
        )
    except asyncio.CancelledError:
        logging.info("Shutdown received, cancelling tasks")
    finally:
        # Required tasks
        receive_task.cancel()
        heartbeat_task.cancel()

        # Extra tasks
        spectrometer_task.cancel()

        # propagate cancellation
        await asyncio.sleep(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=float, default=1.0, help="Heartbeat interval in seconds")
    parser.add_argument("--sub_url", type=str, default="tcp://127.0.0.1:5555", help="ZMQ SUB socket URL")
    parser.add_argument("--serial_port", type=str, default="/dev/ttyACM0", help="Serial port for spectrometer Arduino")
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.sub_url, args.serial_port))
