# supervisor/process_manager.py

import asyncio
import json
import sys
from typing import Dict

from supervisor.config_loader import Subsystem, load_config

cfg = load_config()
HEARTBEAT_INTERVAL = cfg.get("HEARTBEAT_INTERVAL", 10.0)


class ProcessManager:
    """
    Responsible ONLY for process lifecycle management.
    No restart policy.
    No heartbeat timeout logic.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        subsystems: Dict[str, Subsystem],
        telemetry_socket,
        logger,
        command_callback=None,
    ):
        self.loop = loop
        self.subsystems = subsystems
        self.telemetry_socket = telemetry_socket
        self.log = logger

        # Optional callback into Supervisor for SYSTEM CMD
        self.command_callback = command_callback

    # ============================================================
    # PUBLIC API
    # ============================================================

    async def start_all(self):
        """
        Start subsystems in priority tiers.
        """

        tiers = {
            1: [],
            2: [],
            3: []
        }

        for sub in self.subsystems.values():
            if 0 <= sub.priority_rank <= 9:
                tiers[1].append(sub)
            elif 10 <= sub.priority_rank <= 99:
                tiers[2].append(sub)
            else:
                tiers[3].append(sub)

        for tier in [1, 2, 3]:
            if not tiers[tier]:
                continue

            self.log.info(
                f"Launching TIER {tier}: {[s.name for s in tiers[tier]]}"
            )

            await asyncio.gather(*(self.start(sub) for sub in tiers[tier]))

    async def start(self, sub: Subsystem):
        """
        Start a single subsystem.
        """

        if sub.process and sub.process.returncode is None:
            self.log.warning(f"{sub.name} already running")
            return

        cmd = [
            sys.executable,
            "-u",
            str(sub.path),
            "--heartbeat",
            str(HEARTBEAT_INTERVAL),
        ]

        if sub.extra_args:
            cmd.extend(sub.extra_args)

        try:
            sub.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            sub.last_heartbeat = self.loop.time()
            sub.intentionally_stopped = False

            self.log.success(f"{sub.name} started")

            # Start stream readers
            asyncio.create_task(self._read_stream(sub, sub.process.stdout))
            asyncio.create_task(self._read_stream(sub, sub.process.stderr))

        except Exception as e:
            self.log.error(f"Failed to start {sub.name}: {e}")
            sub.process = None

    async def stop(self, sub: Subsystem):
        """
        Gracefully stop a subsystem.
        """

        if not sub.process:
            self.log.info(f"{sub.name} already stopped")
            return

        sub.intentionally_stopped = True

        await self._terminate(sub)

        self.log.warning(f"{sub.name} stopped")

    async def stop_all(self):
        await asyncio.gather(*(self.stop(sub) for sub in self.subsystems.values()))

    async def kill(self, sub: Subsystem):
        """
        Immediate kill (used by monitor).
        """
        if not sub.process:
            return

        sub.process.kill()
        await sub.process.wait()
        sub.process = None

    # ============================================================
    # INTERNALS
    # ============================================================

    async def _terminate(self, sub: Subsystem):
        """
        Graceful terminate with timeout fallback.
        """

        if not sub.process:
            return

        if sub.process.returncode is None:
            sub.process.terminate()

            try:
                await asyncio.wait_for(sub.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.log.warning(f"{sub.name} did not exit, killing")
                sub.process.kill()
                await sub.process.wait()

        sub.process = None

    async def _read_stream(self, sub: Subsystem, stream, stream_name="stdout"):
        """
        Reads stdout/stderr from subprocess.
        Handles:
        - HEARTBEAT
        - JSON logs
        - SYSTEM CMD
        - telemetry forwarding
        """

        while True:
            line = await stream.readline()
            if not line:
                break

            decoded = line.decode(errors="ignore").strip()

            # -------------------------------------------
            # HEARTBEAT
            # -------------------------------------------
            if decoded == "HEARTBEAT":
                sub.last_heartbeat = self.loop.time()
                continue

            # -------------------------------------------
            # Structured JSON log
            # -------------------------------------------
            level = "INFO"
            message = decoded

            try:
                log_obj = json.loads(decoded)
                message = log_obj.get("msg", "")
                level = log_obj.get("level", "INFO").upper()
            except Exception:
                message = decoded
                level = "ERROR" if stream_name == "stderr" else "INFO"

            if level == "DEBUG":
                continue  # skip console & telemetry

            # -------------------------------------------
            # SYSTEM COMMAND
            # -------------------------------------------
            print(f"Received from {sub.name}: {message}")
            if message.startswith("SYSTEM CMD"):
                parts = message.split()

                if self.command_callback:
                    asyncio.create_task(
                        self.command_callback(parts)
                    )

                continue

            # -------------------------------------------
            # TELEMETRY JSON passthrough
            # -------------------------------------------
            if message.startswith("JSON "):
                self.telemetry_socket.send_string(
                    f"TELEMETRY {message}"
                )
                continue

            # -------------------------------------------
            # Console print
            # -------------------------------------------
            if level == "DEBUG":
                self.log.debug(f"[{sub.name}] {message}")
            elif level == "WARNING":
                self.log.warning(f"[{sub.name}] {message}")
            elif level == "ERROR":
                self.log.error(f"[{sub.name}] {message}")
            elif level == "CRITICAL":
                self.log.critical(f"[{sub.name}] {message}")
            else:
                self.log.info(f"[{sub.name}] {message}")

            # Forward to telemetry
            self.telemetry_socket.send_string(
                f"TELEMETRY {level} [{sub.name}]: {message}"
            )