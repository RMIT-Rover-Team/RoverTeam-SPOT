import asyncio
import datetime
import logging
import struct
from dataclasses import asdict, dataclass, field
from typing import Optional

from sharedlib.models import BoardID, CommandID, ScienceID
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
    sensors: dict[int, float] = field(
        default_factory=dict
    )



class ScienceManager:
    def __init__(
        self,
        payload_master: pyRover,
        logger: Optional[logging.Logger] = None,
    ):
        self.payload_master = payload_master
        self.logger = logger
        self.telemetry = ScienceTelemetry()

    # --- PUBLIC APIS ---
    def get_telemetry_data(self):
        return asdict(self.telemetry)

    def estop(self):
         self.payload_master.estop(BoardID.SCIENCE)

    async def toggle_temp(
        self, motor_id: int, enable: bool
    ) -> None:
        if motor_id != ScienceID.HEATER and motor_id != ScienceID.PELTIER:
            return
        
        self.payload_master.ToggleState(
            BoardID.SCIENCE, motor_id, enable
        )

        self.telemetry.temp_state[motor_id] = enable

    async def set_drill_speed(self, speed: int) -> None:
        self.payload_master.SetMotorSpeed(BoardID.SCIENCE, 0, float(speed))
        self.telemetry.drill = int(speed)

    async def set_stepper_steps(self, motor_id: int, speed: int) -> None:
        if motor_id > 3 or motor_id == 0:
            return

        self.payload_master.SetMotorSpeed(BoardID.SCIENCE, motor_id, float(speed))  
        self.telemetry.stepper_motors[motor_id] = int(speed)

    async def set_heatpad_toggle(self, toggle: bool):
        toggle_bit = 1 if toggle else 0
        self.payload_master.ToggleState(BoardID.SCIENCE, ScienceID.HEATER, toggle_bit)
        self.telemetry.temp_state[ScienceID.HEATER] = toggle
        
    async def refresh_drill_telemetry(self):
        _, speed = self.payload_master.GetMotorSpeed(BoardID.SCIENCE, ScienceID.DRILL)
        self.telemetry.drill = int(speed)

    async def refresh_stepper_telemetry(self, motor_id: int):
        if motor_id > 3 or motor_id == 0:
            return

        _, speed = self.payload_master.GetMotorSpeed(BoardID.SCIENCE, motor_id)
        
        self.telemetry.stepper_motors[motor_id] = int(speed)

    async def refresh_sensor_telemetry(self, channel_id: int):
        if channel_id < 0 or channel_id > 7:
            return

        _, sensor_return = self.payload_master.RequestDataPoint(
            BoardID.SCIENCE, 2, ScienceID.HEATER_SENSOR
        )

        self.telemetry.sensors[channel_id] = sensor_return

        
    def get_drill_speed(self) -> int:
        return self.telemetry.drill

    def get_stepper_steps(self, motor_id: int) -> int:
        return self.telemetry.stepper_motors[motor_id]
    
    def get_sensor_telemetry(self, channel_id: int) -> float:
        return self.telemetry.sensors[channel_id]