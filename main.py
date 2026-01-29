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
SHOW_DEBUG = False

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

        log.info(f"[supervisor]: Launching {sub.name} ({sub.priority_rank})")
        cmd = [
            sys.executable, "-u", str(sub.path),
            "--heartbeat", str(heartbeat_interval),
            "--sub_url", sub_url
        ]

        # Append any extra args from config
        if sub.extra_args:
            cmd.extend(sub.extra_args)

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

            # Print nicely
            color = {
                "DEBUG": "\033[90m",
                "INFO": "\033[0m",
                "WARNING": "\033[93m",
                "ERROR": "\033[31m",
                "CRITICAL": "\033[91;1m"
            }.get(level, "\033[0m")
            print(f"{color}[{sub.name}]: {msg}\033[0m")

    async def monitor_subsystems(self):
        while not self._stopping:
            now = self.loop.time()
            for sub in sorted(self.subsystems.values(), key=lambda s: s.priority_rank):
                # Restart if process is gone
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
            sub.process.terminate()
            try:
                await asyncio.wait_for(sub.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                log.warning(f"[supervisor]: {sub.name} did not exit, killing...")
                sub.process.kill()
                await sub.process.wait()
        sub.process = None

    async def stop_all(self):
        if self._stopping:
            return
        log.info("[supervisor]: Stopping all subsystems...")
        self._stopping = True
        await asyncio.gather(*(self.kill_subsystem(sub) for sub in self.subsystems.values()))
        log.info("[supervisor]: All subsystems have been terminated")

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