import asyncio
import json
import json5
import logging
import signal
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict
import zmq
import zmq.asyncio

# -------------------------
# CONFIG
# -------------------------
SUBSYSTEMS_DIR = Path(__file__).parent / "subprocesses"
HEARTBEAT_INTERVAL = 5.0
HEARTBEAT_TIMEOUT = 10.0
RESTART_DELAY = 2.0
SHOW_DEBUG = False # WARNING!! If you enable this, weird stuff happens because we debug the telemetry which becomes a loop

PORT_INTERPROCESS   = 5555
PORT_TELEMETRY      = 3002
PORT_CAMERAS        = 3001

# -------------------------
# CONSOLE LOGGING
# -------------------------
class AnsiFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[90m",   # grey
        "INFO": "\033[0m",     # default
        "WARNING": "\033[93m", # yellow
        "ERROR": "\033[31m",   # red
        "CRITICAL": "\033[91;1m" # bright red + bold
    }

    def format(self, record: logging.LogRecord):
        color = self.COLORS.get(record.levelname, "\033[0m")
        reset = "\033[0m"
        return f"{color}{record.getMessage()}{reset}"


log = logging.getLogger("supervisor")
handler = logging.StreamHandler()
handler.setFormatter(AnsiFormatter())
log.addHandler(handler)
log.setLevel(SHOW_DEBUG and logging.DEBUG or logging.INFO)

color_map = {
    "DEBUG": "\033[90m",
    "INFO": "\033[0m",
    "WARNING": "\033[93m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[91;1m"
}

# -------------------------
# DATA STRUCTURES
# -------------------------
@dataclass
class Subsystem:
    name: str
    priority_rank: int
    path: Path
    extra_args: list[str] = field(default_factory=list)
    process: Optional[asyncio.subprocess.Process] = None
    last_heartbeat: float = field(default_factory=lambda: 0.0)
    restart_pending: bool = False
    intentionally_stopped: bool = False

# -------------------------
# SUPERVISOR
# -------------------------
class Supervisor:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.subsystems: Dict[str, Subsystem] = {}
        self._stopping = False

        # ZMQ PUB for telemetry
        self.zmq_ctx = zmq.asyncio.Context()
        self.main_pub = self.zmq_ctx.socket(zmq.PUB)
        self.main_pub.bind(f"tcp://127.0.0.1:{PORT_INTERPROCESS}")

        # Startup message
        log.info("\nStarting...")

        log.warning("\n   _______  ____  ______")
        log.warning("  / __/ _ \\/ __ \\/_  __/")
        log.warning(" _\\ \\/ ___/ /_/ / / /")
        log.warning("/___/_/   \\____/ /_/")  
        log.warning("SOFTWARE PLATFORM for\nONBOARD TELEMETRY\n")

        log.info("Designed for the:\n")

        log.warning("⣏⡉ ⡎⢱ ⡇⢸ ⡇ ⡷⣸ ⡎⢱ ⢇⡸")
        log.warning("⠧⠤ ⠣⠪ ⠣⠜ ⠇ ⠇⠹ ⠣⠜ ⠇⠸")
        log.warning("SOFTWARE STACK\n\n")

        self.load_subsystems()

    def load_subsystems(self):
        for folder in SUBSYSTEMS_DIR.iterdir():
            if not folder.is_dir():
                continue

            # Try to find a config file: prefer .json5, fallback to .json
            cfg_file = None
            for ext in ("json5", "json"):
                candidate = folder / f"config.{ext}"
                if candidate.exists():
                    cfg_file = candidate
                    break

            if cfg_file is None:
                continue

            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json5.load(f)
            except Exception as e:
                log.warning(f"[supervisor]: Failed to load {cfg_file}: {e}")
                continue

            name = cfg.get("name", folder.name)
            rank = cfg.get("priority", 5)
            args = cfg.get("args", [])

            if rank < 0:
                continue

            self.subsystems[name] = Subsystem(
                name=name,
                priority_rank=rank,
                path=folder / "process.py",
                extra_args=args
            )

        log.info(f"[supervisor]: Loaded subsystems: {list(self.subsystems.keys())}")


    async def start(self):
        log.info("[supervisor]: Starting all subsystems...")

        # Group subsystems by tiers
        tiers = {
            1: [],  # tier 0-9
            2: [],  # tier 10-99
            3: []   # tier 100+
        }

        for sub in self.subsystems.values():
            if 0 <= sub.priority_rank <= 9:
                tiers[1].append(sub)
            elif 10 <= sub.priority_rank <= 99:
                tiers[2].append(sub)
            else:
                tiers[3].append(sub)

        # Launch each tier sequentially
        for tier_num in [1, 2, 3]:
            tier_subs = tiers[tier_num]
            if not tier_subs:
                continue

            log.info(f"[supervisor]: Launching TIER {tier_num} subsystems: {[s.name for s in tier_subs]}")
            await asyncio.gather(*(self.launch(sub) for sub in tier_subs))
            log.info(f"[supervisor]: TIER {tier_num} subsystems launched successfully")

        # After all tiers launched, start monitoring
        await self.monitor_subsystems()

    async def launch(
        self,
        sub: Subsystem,
        heartbeat_interval=HEARTBEAT_INTERVAL,
        sub_url=f"tcp://127.0.0.1:{PORT_INTERPROCESS}"
    ):
        if not sub.path.exists():
            log.error(f"[supervisor]: process.py file for {sub.name} does not exist.")
            sub.process = None
            return
        
        sub.intentionally_stopped = False

        log.info(f"[supervisor]: Launching {sub.name} ({sub.priority_rank})")
        cmd = [
            sys.executable, "-u", str(sub.path),
            "--heartbeat", str(heartbeat_interval),
            "--sub_url", sub_url
        ]

        # Append any extra args from config
        if sub.extra_args:
            cmd.extend(flatten_args(sub.extra_args))

        try:
            sub.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            sub.last_heartbeat = self.loop.time()
            asyncio.create_task(self.read_stream(sub, sub.process.stdout))
            asyncio.create_task(self.read_stream(sub, sub.process.stderr))
        except Exception as e:
            log.error(f"[supervisor]: Failed to launch {sub.name}: {e}")
            sub.process = None
            sub.restart_pending = True

    async def read_stream(self, sub: Subsystem, stream, stream_name="stdout"):
        """
        Read lines from a subsystem. Heartbeats appear as `[sub]: HEARTBEAT` in grey.
        Normal log lines appear as `[sub]: message` with color based on level if JSON structured.
        """
        if not sub.process or not stream:
            return

        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode(errors="ignore").strip()

            # Heartbeat
            if decoded == "HEARTBEAT":
                sub.last_heartbeat = self.loop.time()
                if not SHOW_DEBUG:
                    continue
                print(f"\033[90m[{sub.name}]: HEARTBEAT\033[0m")  # grey
                continue

            # Attempt JSON decoding (structured log from subsystem)
            try:
                log_obj = json.loads(decoded)
                msg = log_obj.get("msg", "")
                level = log_obj.get("level", "INFO").upper()
            except Exception:
                msg = decoded
                level = "INFO"

            if level == "DEBUG" and not SHOW_DEBUG:
                continue

            # Command
            if msg.startswith("SYSTEM CMD"):
                arg_v = msg.split()
                arg_c = len(arg_v)
                await self.handle_command(arg_c, arg_v)
                continue

            # Print nicely
            color = color_map.get(level, "\033[0m")
            print(f"{color}[{sub.name}]: {msg}\033[0m")

            # Log through telemetry
            self.main_pub.send_string(f"TELEMETRY {level} [{sub.name}]: {msg}")

    async def monitor_subsystems(self):
        while not self._stopping:
            now = self.loop.time()
            for sub in sorted(self.subsystems.values(), key=lambda s: s.priority_rank):

                # Ignore intentionally stopped subsystems
                if sub.intentionally_stopped:
                    continue

                # Restart if process is gone unexpectedly
                if sub.process is None and not sub.restart_pending:
                    sub.restart_pending = True
                    asyncio.create_task(self.restart_subsystem(sub))
                    continue

                # Heartbeat timeout
                if sub.process and (now - sub.last_heartbeat > HEARTBEAT_TIMEOUT):
                    log.warning(f"[supervisor]: Heartbeat lost: {sub.name}, restarting...")
                    await self.kill_subsystem(sub)
                    asyncio.create_task(self.restart_subsystem(sub))
                    continue

                # Process exit
                if sub.process and sub.process.returncode is not None:
                    log.warning(f"[supervisor]: {sub.name} exited with {sub.process.returncode}, restarting...")
                    asyncio.create_task(self.restart_subsystem(sub))

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def restart_subsystem(self, sub: Subsystem):
        if sub.restart_pending:
            sub.restart_pending = False
            await asyncio.sleep(RESTART_DELAY)
            await self.launch(sub)

    async def kill_subsystem(self, sub: Subsystem):
        if sub.process and sub.process.returncode is None:
            log.info(f"[supervisor]: Terminating {sub.name}...")

            # Terminate process gracefully
            sub.process.terminate()

            try:
                # Wait up to 5 seconds for exit
                await asyncio.wait_for(sub.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                log.warning(f"[supervisor]: {sub.name} did not exit, killing...")
                sub.process.kill()
                await sub.process.wait()

            # Ensure stdout/stderr tasks are drained
            await asyncio.sleep(0.1)

        sub.process = None


    async def force_restart_subsystem(self, sub: Subsystem):
        """
        Stop, clean up, and launch a subsystem again.
        Waits for proper shutdown before launching.
        """
        log.info(f"[supervisor]: Force restarting {sub.name}...")

        # Stop first
        await self.stop_subsystem(sub)

        # Small delay to ensure OS releases port (Windows)
        await asyncio.sleep(0.1)

        # Launch again
        await self.launch(sub)

        log.info(f"[supervisor]: {sub.name} restarted successfully")


    async def stop_subsystem(self, sub: Subsystem):
        """
        Stop a specific subsystem and ensure heartbeat monitoring is stopped.
        Fully waits for process cleanup so TCP ports are freed.
        """
        if sub.process is None:
            log.info(f"[supervisor]: {sub.name} is already stopped")
            return

        log.info(f"[supervisor]: Stopping {sub.name}...")

        # Prevent auto-restart while stopping
        sub.restart_pending = False
        sub.intentionally_stopped = True

        # Kill the process
        await self.kill_subsystem(sub)

        # Reset last heartbeat
        sub.last_heartbeat = 0.0

        log.info(f"[supervisor]: {sub.name} has been stopped successfully")


    async def stop_all(self):
        if self._stopping:
            return
        log.info("[supervisor]: Stopping all subsystems...")
        self._stopping = True
        await asyncio.gather(*(self.kill_subsystem(sub) for sub in self.subsystems.values()))
        log.info("[supervisor]: All subsystems have been terminated")

    async def handle_command(self, arg_c: int, arg_v):
        return_message = "Invalid command"
        return_level = "ERROR"
        if arg_c <= 2:
            return_message = "No command specified"
        
        # restart
        elif arg_v[2] == "restart":
            if arg_c <= 3:
                return_message = "No process specified"
            elif next((sub for sub in self.subsystems.values() if sub.name == arg_v[3]), None) == None:
                return_message = f"The process '{arg_v[3]}' cannot be found."
            else:
                sub = next((sub for sub in self.subsystems.values() if sub.name == arg_v[3]), None)
                if sub == None:
                    return_message = f"Error getting process '{arg_v[3]}'."
                else:
                    return_message = f"Restarted {arg_v[3]}"
                    return_level = "WARNING"
                    await self.force_restart_subsystem(sub)

        # stop
        elif arg_v[2] == "stop":
            if arg_c <= 3:
                return_message = "No process specified"
            elif arg_v[3] == "telemetry":
                # HARDCODE BLOCK - this would brick the comms to the rover lol
                return_message = "BLOCKED: Stopping telemetry is irrecoverable. Use 'restart telemetry' instead."
            elif next((sub for sub in self.subsystems.values() if sub.name == arg_v[3]), None) == None:
                return_message = f"The process '{arg_v[3]}' cannot be found."
            else:
                sub = next((sub for sub in self.subsystems.values() if sub.name == arg_v[3]), None)
                if sub == None:
                    return_message = f"Error getting process '{arg_v[3]}'."
                else:
                    return_message = f"Stopped {arg_v[3]}"
                    return_level = "WARNING"
                    await self.stop_subsystem(sub)

        # start
        elif arg_v[2] == "start":
            if arg_c <= 3:
                return_message = "No process specified"
            elif next((sub for sub in self.subsystems.values() if sub.name == arg_v[3]), None) == None:
                return_message = f"The process '{arg_v[3]}' cannot be found."
            else:
                sub = next((sub for sub in self.subsystems.values() if sub.name == arg_v[3]), None)
                if sub == None:
                    return_message = f"Error getting process '{arg_v[3]}'."
                else:
                    if not sub.process == None:
                        return_message = f"{arg_v[3]} is already running. Try 'restart {arg_v[3]}' instead."
                        return_level = "ERROR"
                    else:
                        return_message = f"Started {arg_v[3]}"
                        return_level = "WARNING"
                        await self.launch(sub)
        
        self.main_pub.send_string(f"TELEMETRY ERROR [supervisor]: {return_message}")
        color = color_map.get(return_level, "\033[0m")
        print(f"{color}[supervisor]: {return_message}\033[0m")

# -------------------------
# Arg helper function
# -------------------------
def flatten_args(args: dict[str, object]) -> list[str]:
    result: list[str] = []

    for key, value in args.items():
        if value is None:
            continue

        # Boolean flag
        if isinstance(value, bool):
            if value:
                result.append(key)
            continue

        # List → repeat flag
        if isinstance(value, list):
            for item in value:
                result.append(key)
                result.append(str(item))
            continue

        # Everything else → single value
        result.append(key)
        result.append(str(value))

    return result

# -------------------------
# MAIN
# -------------------------
def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    supervisor = Supervisor()

    def shutdown(*args):
        log.error("[supervisor]: Received shutdown signal")
        asyncio.create_task(supervisor.stop_all())

    # Cross-platform signals
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, shutdown)
    else:
        loop.add_signal_handler(signal.SIGINT, shutdown)
        loop.add_signal_handler(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(supervisor.start())
    finally:
        loop.run_until_complete(supervisor.stop_all())
        loop.close()


if __name__ == "__main__":
    main()