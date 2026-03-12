import asyncio
import datetime
import logging
import struct
from dataclasses import field, asdict
from typing import List, Optional, Union

from dataclasses import dataclass, field, asdict

from sharedlib.models import BoardID, CommandID, ScienceID
from sharedlib.canbus.client import CANClient
from sharedlib.payloadControl import pyRover

# from models import
# imu 4


@dataclass()
class ScienceTelemetry:
    drill: int = 0
    stepper_motors: dict[int, int] = field(
        default_factory=lambda: {
            ScienceID.AUGER: 0,
            ScienceID.MICROSCOPE: 0,
            ScienceID.MICROSCOPE_SWIVEL: 0,
        }
    )
    temp_state: dict[int, bool] = field(
        default_factory=lambda: {
            ScienceID.HEATER: False,
            ScienceID.PELTIER: False
        }
    )



class ScienceManager:
    def __init__(
        self,
        payload_master: pyRover,
        logger: Optional[logging.Logger] = None,
    ):
        self.payload_master = payload_master

        self.logger = logger
        self.id = 12

        self.telemetry = ScienceTelemetry()

        # validation
        self._valid_cmd_ids = {
            CommandID.ESTOP,
            CommandID.TOGGLE, 
            CommandID.SETSPEED,
            CommandID.GETSPEED,
        }


    # --- PUBLIC APIS ---
    def get_telemetry_data(self):
        return asdict(self.telemetry)

    async def estop(self):
        await self.payload_master.estop(BoardID.SCIENCE)

    async def toggle_temp(
        self, motor_id: int, enable: bool
    ) -> None:
        if motor_id != ScienceID.HEATER and motor_id != ScienceID.PELTIER:
            return
        
        await self.payload_master.ToggleState(
            BoardID.SCIENCE, motor_id, enable
        )

        self.telemetry.temp_state[motor_id] = enable

    async def set_drill_speed(self, speed: int) -> None:
        await self.payload_master.SetMotorSpeed(BoardID.SCIENCE, 0, float(speed))
        self.telemetry.drill = int(speed)

    async def set_stepper_steps(self, motor_id: int, speed: int) -> None:
        if motor_id > 3 or motor_id == 0:
            return

        await self.payload_master.SetMotorSpeed(BoardID.SCIENCE, motor_id, float(speed))
        self.telemetry.stepper_motors[motor_id] = int(speed)

    async def refresh_drill_telemetry(self):
        _, speed = await self.payload_master.GetMotorSpeed(BoardID.SCIENCE, 0)
        self.telemetry.drill = speed

    async def refresh_stepper_telemetry(self, motor_id: int):
        if motor_id > 3 or motor_id == 0:
            return -1
        _, speed = await self.payload_master.GetMotorSpeed(BoardID.SCIENCE, motor_id)
        self.telemetry.stepper_motors[motor_id] = int(speed)
        
    async def get_drill_speed(self) -> int:
        return self.telemetry.drill

    async def get_stepper_steps(self, motor_id: int) -> int:
        return self.telemetry.stepper_motors[motor_id]

    # --- Internal functions ---
    # --- PARSING MSG
    @staticmethod
    def _parse_arbitration_id(arbitration_id: int) -> tuple[int, int]:
        dest_id = (arbitration_id >> 6) & 0x3F
        src_id = arbitration_id & 0x3F

        return dest_id, src_id

    def _parse_can_msg(
        self, msg_id: int, data: bytes
    ) -> tuple[int, int, int, int, int, float]:
        dest_id, src_id = self._parse_arbitration_id(msg_id)
        cmd_id = (data[0] >> 4) & 0x0F
        stream_id = data[0] & 0x0F
        channel_id = (data[1] >> 4) & 0x0F
        return_value = struct.unpack_from("<f", data, 2)[0]
        return dest_id, src_id, cmd_id, stream_id, channel_id, return_value

    # --- MISC HELPERS
    @staticmethod
    def _build_arbitration_id(dest_id: int, src_id: int) -> int:
        return ((dest_id & 0x3F) << 6) | (src_id & 0x3F)
