# supervisor/monitor.py

import asyncio
from typing import Dict

from supervisor.config_loader import Subsystem, load_config
from supervisor.process_manager import ProcessManager

cfg = load_config()
HEARTBEAT_TIMEOUT = cfg.get("HEARTBEAT_TIMEOUT", 20.0)
RESTART_DELAY = cfg.get("RESTART_DELAY", 2.0)
MONITOR_INTERVAL = cfg.get("MONITOR_INTERVAL", 5.0)

class Monitor:
    """
    Responsible for:
    - Heartbeat timeout detection
    - Detecting unexpected exits
    - Scheduling restarts

    Does NOT manage lifecycle directly.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        subsystems: Dict[str, Subsystem],
        process_manager: ProcessManager,
        logger,
    ):
        self.loop = loop
        self.subsystems = subsystems
        self.pm = process_manager
        self.log = logger

        self._stopping = False

    # ============================================================
    # PUBLIC ENTRYPOINT
    # ============================================================

    async def run(self):
        """
        Main monitor loop.
        Runs until supervisor shutdown.
        """

        self.log.info("Monitor started")

        while not self._stopping:

            now = self.loop.time()

            # Sort by priority so lower rank restarts first
            for sub in sorted(
                self.subsystems.values(),
                key=lambda s: s.priority_rank,
            ):
                await self._check_subsystem(sub, now)

            await asyncio.sleep(MONITOR_INTERVAL)

        self.log.info("Monitor stopped")

    def stop(self):
        self._stopping = True

    # ============================================================
    # INTERNAL CHECK LOGIC
    # ============================================================

    async def _check_subsystem(self, sub: Subsystem, now: float):

        # --------------------------------------------------------
        # Skip intentionally stopped
        # --------------------------------------------------------
        if sub.intentionally_stopped:
            return

        # --------------------------------------------------------
        # Process never started or crashed completely
        # --------------------------------------------------------
        if sub.process is None:
            if not sub.restart_pending:
                await self._schedule_restart(sub)
            return

        # --------------------------------------------------------
        # Process exited unexpectedly
        # --------------------------------------------------------
        if sub.process.returncode is not None:
            self.log.warning(
                f"{sub.name} exited with code {sub.process.returncode}"
            )

            await self._schedule_restart(sub)
            return

        # --------------------------------------------------------
        # Heartbeat timeout
        # --------------------------------------------------------
        if now - sub.last_heartbeat > HEARTBEAT_TIMEOUT:
            self.log.warning(
                f"Heartbeat timeout for {sub.name}"
            )

            await self.pm.kill(sub)
            await self._schedule_restart(sub)

    # ============================================================
    # RESTART LOGIC
    # ============================================================

    async def _schedule_restart(self, sub: Subsystem):

        if sub.restart_pending:
            return

        sub.restart_pending = True

        async def _restart():
            await asyncio.sleep(RESTART_DELAY)

            sub.restart_pending = False

            if not sub.intentionally_stopped:
                self.log.warning(f"Restarting {sub.name}")
                await self.pm.start(sub)

        asyncio.create_task(_restart())