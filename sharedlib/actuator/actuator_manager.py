import asyncio
from typing import Dict, List
from sharedlib.canbus.client import CANClient
from .actuator_base import Actuator


class ActuatorManager:
    def __init__(self, can_client: CANClient, rate_hz: float = 20.0):
        self.can = can_client
        self.rate = rate_hz
        self.actuators: Dict[str, Actuator] = {}

    def register(self, actuator: Actuator):
        self.actuators[actuator.name] = actuator

        if actuator.motor_id is not None:
            self.can.subscribe(
                actuator.motor_id + 0x100,
                lambda data, a=actuator: a.handle_can_message(
                    actuator.motor_id + 0x100, data
                ),
            )

    async def loop(self):
        interval = 1.0 / self.rate

        while True:
            # Send velocity updates
            for actuator in self.actuators.values():
                cmd = actuator.build_velocity_command()
                if cmd:
                    await self.can.send(*cmd)

            # Send one broadcast position request
            # (Only if at least one MyActuator exists)
            for actuator in self.actuators.values():
                cmd = actuator.build_position_request()
                if cmd:
                    await self.can.send(*cmd)
                    break  # Only send once

            await asyncio.sleep(interval)