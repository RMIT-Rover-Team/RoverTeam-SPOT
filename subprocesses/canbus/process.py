import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path

import zmq
import zmq.asyncio

# -------------------------
# CAN IMPORT
# -------------------------
try:
    import can  # python-can driver

    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False


# -------------------------
# LOGGING
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if hasattr(record, "data"):
            log_obj["data"] = record.data
        if hasattr(record, "error"):
            log_obj["error"] = record.error
        print(json.dumps(log_obj), flush=True)


logger = logging.getLogger("canbus")
logger.setLevel(logging.DEBUG)
logger.addHandler(JsonHandler())

# -------------------------
# WINDOWS EVENT LOOP FIX
# -------------------------
if sys.platform.startswith("win"):
    from asyncio import WindowsSelectorEventLoopPolicy

    asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

# -------------------------
# ARGUMENT PARSER
# -------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--heartbeat", type=float, default=1.0)
parser.add_argument("--can_channel", type=str, default="can0")
parser.add_argument("--can_type", type=str, default="socketcan")
parser.add_argument("--pub_port", type=int, default=5556)
parser.add_argument("--rep_port", type=int, default=5557)
args, unknown_args = parser.parse_known_args()


# -------------------------
# CAN DAEMON
# -------------------------
class CANDaemon:
    def __init__(self, channel, bustype, pub_port, rep_port, pull_port=5560):
        self.ctx = zmq.asyncio.Context()

        # PUB: broadcasts incoming CAN messages
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(f"tcp://127.0.0.1:{pub_port}")

        # REP: blocking client send
        self.rep = self.ctx.socket(zmq.REP)
        self.rep.bind(f"tcp://127.0.0.1:{rep_port}")

        # PULL: fire-and-forget client send
        self.pull = self.ctx.socket(zmq.PULL)
        self.pull.bind(f"tcp://127.0.0.1:{pull_port}")

        self._listeners = {}
        self.running = True
        self.state = "DOWN"

        # CAN bus init...
        if CAN_AVAILABLE:
            try:
                self.bus = can.interface.Bus(channel=channel, interface=bustype)
                self.state = "UP"
                logger.info(
                    "CAN bus initialized",
                    extra={"data": {"channel": channel, "interface": bustype}},
                )
            except Exception as e:
                self.bus = None
                self.state = "DOWN"
                logger.error("No CAN Bus Support on Hardware", extra={"error": str(e)})
        else:
            self.bus = None
            logger.error("No CAN Bus Support on Hardware")

    async def start(self):
        self.recv_task = asyncio.create_task(self._recv_can_loop())
        self.rep_task = asyncio.create_task(self._rep_loop())
        self.pull_task = asyncio.create_task(self._pull_loop())
        await asyncio.gather(self.recv_task, self.rep_task)

    async def _recv_can_loop(self):
        loop = asyncio.get_running_loop()
        if not self.bus:
            while self.running:
                await asyncio.sleep(1)
            return

        def bus_iter():
            # blocking iterator
            return iter(self.bus)

        bus_iterator = bus_iter()
        while self.running:
            try:
                msg = await loop.run_in_executor(None, lambda: next(bus_iterator, None))
                if msg is None:
                    await asyncio.sleep(0.01)
                    continue
                topic = str(msg.arbitration_id).encode()
                self.pub.send_multipart([topic, msg.data])
                if msg.arbitration_id in self._listeners:
                    cb = self._listeners[msg.arbitration_id]
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.run_coroutine_threadsafe(cb(msg), loop)
                    else:
                        cb(msg)
            except Exception as e:
                logger.warning("Error in CAN receive loop", extra={"error": str(e)})
                await asyncio.sleep(0.01)

    async def _rep_loop(self):
        while self.running:
            try:
                msg = await self.rep.recv_multipart()
                # special query: get bus state
                if msg[0] == b"__STATE__":
                    await self.rep.send_string(self.state)
                    continue

                if not self.bus:
                    await self.rep.send_string("DOWN")
                    continue

                msg_id = int(msg[0])
                data = msg[1]
                can_msg = can.Message(
                    arbitration_id=msg_id, data=data, is_extended_id=False
                )
                self.bus.send(can_msg)
                await self.rep.send_string("OK")
            except Exception as e:
                logger.warning("Error handling client send", extra={"error": str(e)})
                try:
                    await self.rep.send_string("ERROR")
                except:
                    pass

    async def _pull_loop(self):
        """Process fire-and-forget CAN messages from clients (PUSH)"""
        while self.running:
            try:
                msg = await self.pull.recv_multipart()
                if not self.bus:
                    continue
                msg_id = int(msg[0])
                data = msg[1]
                can_msg = can.Message(
                    arbitration_id=msg_id, data=data, is_extended_id=False
                )
                self.bus.send(can_msg)
            except Exception as e:
                logger.warning(
                    f"Error handling push send: {e}", extra={"error": str(e)}
                )
                await asyncio.sleep(0.001)

    async def stop(self):
        self.running = False
        # Cancel tasks with timeout
        for task in [self.recv_task, self.rep_task, self.pull_task]:
            if task:
                task.cancel()
        await asyncio.sleep(0.1)
        self.pub.close()
        self.rep.close()
        self.pull.close()
        self.ctx.term()
        logger.info("CAN daemon stopped")


# -------------------------
# HEARTBEAT
# -------------------------
async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)


# -------------------------
# MAIN
# -------------------------
async def main():
    daemon = CANDaemon(
        channel=args.can_channel,
        bustype=args.can_type,
        pub_port=args.pub_port,
        rep_port=args.rep_port,
    )
    heartbeat_task = asyncio.create_task(heartbeat_loop(args.heartbeat))

    try:
        await daemon.start()
    except asyncio.CancelledError:
        logger.info("Shutdown received, cancelling tasks")
    finally:
        heartbeat_task.cancel()
        await daemon.stop()
        await asyncio.sleep(0)


if __name__ == "__main__":
    asyncio.run(main())
