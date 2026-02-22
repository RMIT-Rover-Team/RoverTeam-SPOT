# supervisor/core.py

import asyncio
from pathlib import Path
from typing import Dict

import zmq
import zmq.asyncio

from supervisor.logging import get_logger
from supervisor.config_loader import load_config, load_subsystems, Subsystem
from supervisor.process_manager import ProcessManager
from supervisor.monitor import Monitor
from supervisor.command_handler import CommandHandler

cfg = load_config()
PORT_INTERPROCESS = cfg.get("PORT_INTERPROCESS", 5555)

def get_git_branch_commit():
    """
    Returns a tuple (branch, commit) by reading .git folder.
    Fallback: ("-", "-")
    """
    git_dir = Path(__file__).parent.parent / ".git"
    head_file = git_dir / "HEAD"
    if not head_file.exists():
        return "-", "-"

    try:
        head_content = head_file.read_text().strip()
        if head_content.startswith("ref:"):
            ref_path = head_content.split(" ")[1]
            branch = Path(ref_path).name
            ref_file = git_dir / ref_path
            commit = ref_file.read_text().strip()[:7] if ref_file.exists() else "-"
        else:
            branch = "DETACHED"
            commit = head_content[:7]
        return branch, commit
    except Exception:
        return "-", "-"


class Supervisor:
    """
    High-level orchestration only.
    No implementation logic lives here.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self._stopping = False

        # -------------------------------------------------
        # Logging
        # -------------------------------------------------
        self.log = get_logger()

        # -------------------------------------------------
        # ZMQ Setup
        # -------------------------------------------------
        self.zmq_ctx = zmq.asyncio.Context()
        self.main_pub = self.zmq_ctx.socket(zmq.PUB)
        self.main_pub.bind(f"tcp://127.0.0.1:{PORT_INTERPROCESS}")

        # -------------------------------------------------
        # Load subsystem definitions
        # -------------------------------------------------
        self.subsystems: Dict[str, Subsystem] = load_subsystems()

        # -------------------------------------------------
        # Initialise modules
        # -------------------------------------------------
        # 1️⃣ Create ProcessManager first without callback
        self.process_manager = ProcessManager(
            loop=self.loop,
            subsystems=self.subsystems,
            telemetry_socket=self.main_pub,
            logger=self.log,
        )

        # 2️⃣ Create CommandHandler with process_manager set
        self.command_handler = CommandHandler(
            supervisor=self,
            process_manager=self.process_manager,
            logger=self.log,
        )

        # 3️⃣ Now pass command_callback into ProcessManager
        self.process_manager.command_callback = self.command_handler.handle

        self.monitor = Monitor(
            loop=self.loop,
            subsystems=self.subsystems,
            process_manager=self.process_manager,
            logger=self.log,
        )

        # -------------------------------------------------
        # Startup message with Git branch and commit
        # -------------------------------------------------
        branch, commit = get_git_branch_commit()
        
        self.log.warning("\n   _______  ____  ______")
        self.log.warning("  / __/ _ \\/ __ \\/_  __/")
        self.log.warning(" _\\ \\/ ___/ /_/ / / /")
        self.log.warning("/___/_/   \\____/ /_/")  
        self.log.warning("SOFTWARE PLATFORM for")
        self.log.warning("ONBOARD TELEMETRY\n")

        self.log.log(level=25, msg=f"{branch} @ {commit}\n")

        self.log.info("Supported by the:")
        self.log.warning("⣏⡉ ⡎⢱ ⡇⢸ ⡇ ⡷⣸ ⡎⢱ ⢇⡸")
        self.log.warning("⠧⠤ ⠣⠪ ⠣⠜ ⠇ ⠇⠹ ⠣⠜ ⠇⠸")
        self.log.warning("SOFTWARE STACK\n")

    # ============================================================
    # STARTUP
    # ============================================================
    async def start(self):
        self.log.info("Starting supervisor...")

        await self.process_manager.start_all()

        # Monitoring runs forever until shutdown
        await self.monitor.run()

    # ============================================================
    # SHUTDOWN
    # ============================================================
    async def shutdown(self):
        if self._stopping:
            return

        self._stopping = True
        self.log.warning("Supervisor shutting down...")

        # Stop all running subprocesses
        await self.process_manager.stop_all()

        # Cancel any tasks created by monitor/process manager if needed
        # (Optional, depending on your modules)
        tasks = [t for t in asyncio.all_tasks(self.loop) if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # Close ZMQ sockets cleanly
        self.main_pub.close()
        self.zmq_ctx.term()

        self.log.info("Supervisor shutdown complete")

    # ============================================================
    # COMMAND ENTRYPOINT (called from process_manager stream reader)
    # ============================================================
    async def handle_command(self, args):
        await self.command_handler.handle(args)