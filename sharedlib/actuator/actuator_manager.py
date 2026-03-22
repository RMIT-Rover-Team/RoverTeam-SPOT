import asyncio
from typing import Dict, Iterable, Tuple, Optional, Union

from sharedlib.canbus.client import CANClient
from .actuator_base import Actuator


# -------------------------------------------------
# Type aliases
# -------------------------------------------------
CANCommand = Tuple[int, bytes]
MaybeCommands = Optional[
    Union[
        CANCommand,
        Iterable[CANCommand],
    ]
]


class ActuatorManager:
    def __init__(self, can_client: CANClient, rate_hz: float = 20.0):
        self.can = can_client
        self.rate = rate_hz
        self.actuators: Dict[str, Actuator] = {}

    # -------------------------------------------------
    # Register
    # -------------------------------------------------
    def register(self, actuator: Actuator):
        self.actuators[actuator.name] = actuator

        # New-style subscription (ODrive etc)
        if hasattr(actuator, "subscribe_ids"):
            for msg_id in actuator.subscribe_ids():
                self.can.subscribe(
                    msg_id,
                    lambda data, a=actuator, mid=msg_id: a.handle_can_message(mid, data),
                )
            return

        # Legacy MyActuator subscription
        if actuator.motor_id is not None:
            msg_id = actuator.motor_id + 0x100
            self.can.subscribe(
                msg_id,
                lambda data, a=actuator, mid=msg_id: a.handle_can_message(mid, data),
            )

    # -------------------------------------------------
    # Internal: Send single or multiple commands
    # -------------------------------------------------
    async def _send_commands(self, cmds: MaybeCommands):
        if not cmds:
            return

        # Single command: (can_id, data)
        if isinstance(cmds, tuple):
            await self.can.send(*cmds)
            return

        # Iterable of commands
        for cmd in cmds:
            if cmd:
                await self.can.send(*cmd)

    # -------------------------------------------------
    # Main loop
    # -------------------------------------------------
    async def loop(self):
        interval = 1.0 / self.rate

        while True:
            for actuator in self.actuators.values():

                # -----------------------------------------
                # Axis state command (ODrive only)
                # -----------------------------------------
                if hasattr(actuator, "build_axis_state_command"):
                    cmd = actuator.build_axis_state_command()
                    await self._send_commands(cmd)

                # -----------------------------------------
                # Velocity / Position
                # -----------------------------------------
                if actuator.target_mode == 0:
                    cmd = actuator.build_velocity_command()
                else:
                    cmd = actuator.build_position_command()

                await self._send_commands(cmd)

            # ---------------------------------------------
            # Position request (MyActuator only)
            # Send ONE broadcast per cycle
            # ---------------------------------------------
            for actuator in self.actuators.values():
                if hasattr(actuator, "build_position_request"):
                    cmd = actuator.build_position_request()
                    if cmd:
                        await self._send_commands(cmd)
                        break

            await asyncio.sleep(interval)