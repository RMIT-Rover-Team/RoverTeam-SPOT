# supervisor/command_handler.py

from typing import List


class CommandHandler:
    """
    Handles SYSTEM CMD commands coming from subprocesses.
    Does NOT manage lifecycle directly — delegates to ProcessManager.
    """

    def __init__(self, supervisor, process_manager, logger):
        self.supervisor = supervisor
        self.pm = process_manager
        self.log = logger

        self._restart_all_confirmation = False

    # ============================================================
    # PUBLIC ENTRYPOINT
    # ============================================================

    async def handle(self, args: List[str]):
        """
        Args come in already split:
        Example:
            ["SYSTEM", "CMD", "restart", "drive"]
        """

        if len(args) < 3:
            self._reply("No command specified", level="ERROR")
            return

        command = args[2]

        # --------------------------------------------------------
        # Confirmation state (restart-all)
        # --------------------------------------------------------
        if self._restart_all_confirmation:
            await self._handle_restart_all_confirmation(args)
            return

        # --------------------------------------------------------
        # restart <subsystem>
        # --------------------------------------------------------
        if command == "restart":
            await self._restart(args)
            return

        # --------------------------------------------------------
        # stop <subsystem>
        # --------------------------------------------------------
        if command == "stop":
            await self._stop(args)
            return

        # --------------------------------------------------------
        # start <subsystem>
        # --------------------------------------------------------
        if command == "start":
            await self._start(args)
            return

        # --------------------------------------------------------
        # restart-all
        # --------------------------------------------------------
        if command == "restart-all":
            self._restart_all_confirmation = True
            self._reply(
                "WARNING: restart-all will terminate supervisor. "
                "Systemd must restart it. Confirm? [y/n]",
                level="WARNING",
            )
            return
        
        if command == "help":
            await self._help(args)
            return

        self._reply(f"Unknown command: {command}", level="ERROR")

    # ============================================================
    # COMMAND IMPLEMENTATIONS
    # ============================================================

    async def _help(self, args: list[str]):
        """
        Responds with a list of available commands and usage.
        """
        help_msg = """
Available commands:
start <process>          - Start a subsystem
stop <process>           - Stop a subsystem
restart <process>        - Restart a subsystem
restart-all              - Restart the supervisor process
help                     - Show this help message
Notes:
- 'telemetry' cannot be stopped manually.
- Use 'restart-all' with caution; confirm with 'y'.\n
"""
        self._reply(help_msg.strip(), level="INFO")

    async def _restart(self, args: List[str]):
        if len(args) < 4:
            self._reply("No process specified", level="ERROR")
            return

        name = args[3]
        sub = self._get_subsystem(name)

        if not sub:
            self._reply(f"Process '{name}' not found", level="ERROR")
            return

        try:
            await self.pm.stop(sub)
        except Exception as e:
            self._reply(f"Failed to stop {name}: {e}", level="ERROR")
            return

        try:
            await self.pm.start(sub)
        except Exception as e:
            self._reply(f"Failed to start {name}: {e}", level="ERROR")
            return

        self._reply(f"Restarted {name}", level="WARNING")

    async def _stop(self, args: List[str]):
        if len(args) < 4:
            self._reply("No process specified", level="ERROR")
            return

        name = args[3]

        if name == "telemetry":
            self._reply(
                "BLOCKED: Stopping telemetry is irrecoverable. "
                "Use 'restart telemetry' instead.",
                level="ERROR",
            )
            return

        sub = self._get_subsystem(name)
        if not sub:
            self._reply(f"Process '{name}' not found", level="ERROR")
            return

        # Mark as intentionally stopped so monitor ignores heartbeat loss
        sub.intentionally_stopped = True

        try:
            await self.pm.stop(sub)
            self._reply(f"Stopped {name}", level="WARNING")
        except Exception as e:
            self._reply(f"Failed to stop {name}: {e}", level="ERROR")

    async def _start(self, args: List[str]):
        if len(args) < 4:
            self._reply("No process specified", level="ERROR")
            return

        name = args[3]
        sub = self._get_subsystem(name)
        if not sub:
            self._reply(f"Process '{name}' not found", level="ERROR")
            return

        if sub.process and sub.process.returncode is None:
            self._reply(
                f"{name} already running. Use 'restart {name}' instead.",
                level="ERROR",
            )
            return

        try:
            await self.pm.start(sub)
            self._reply(f"Started {name}", level="WARNING")
        except Exception as e:
            self._reply(f"Failed to start {name}: {e}", level="ERROR")


    async def _handle_restart_all_confirmation(self, args: List[str]):
        self._restart_all_confirmation = False

        if len(args) >= 3 and args[2].lower() == "y":
            self._reply("Shutting down supervisor...", level="CRITICAL")
            try:
                await self.supervisor.shutdown()
            except Exception as e:
                self._reply(f"Error during shutdown: {e}", level="ERROR")
        else:
            self._reply("Restart-all cancelled", level="INFO")

    # ============================================================
    # HELPERS
    # ============================================================

    def _get_subsystem(self, name):
        return self.supervisor.subsystems.get(name)

    def _reply(self, message: str, level: str = "INFO"):
        """
        Print + forward to telemetry via supervisor socket.
        """

        # Console
        if level == "DEBUG":
            self.log.debug(message)
        elif level == "WARNING":
            self.log.warning(message)
        elif level == "ERROR":
            self.log.error(message)
        elif level == "CRITICAL":
            self.log.critical(message)
        else:
            self.log.info(message)

        # Telemetry
        self.supervisor.main_pub.send_string(
            f"TELEMETRY {level} [supervisor]: {message}"
        )