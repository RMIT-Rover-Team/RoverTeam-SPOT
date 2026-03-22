import time
from typing import Optional
from .actuator_base import Actuator
from sharedlib.payloadControl import pyRover

PayloadID = 0xB

class PayloadActuator(Actuator):
    def __init__(self, name: str, motor_id: int):
        super().__init__(name, motor_id)
        # -------------------------
        # Connect to the payload
        # -------------------------
        self._payloadMaster = pyRover.PyRover("can0",1)
        self.motor_id = motor_id

    def set_velocity(self, velocity: float):
        self._payloadMaster.SetMotorSpeed(PayloadID, self.motor_id, velocity)

    def set_position(self, position: float):
        self._payloadMaster.SetMotorPosition(PayloadID, self.motor_id, position)

    def get_position(self) -> float:
        return self._payloadMaster.GetMotorPosition(PayloadID, self.motor_id)

    def get_velocity(self) -> float:
        return self._payloadMaster.GetMotorSpeed(PayloadID, self.motor_id)


    # -------------------------
    # CAN interface returns None
    # These keep the interpreter happy
    # -------------------------
    def build_velocity_command(self) -> Optional[tuple[int, bytes]]:
        return None

    def build_position_command(self) -> Optional[tuple[int, bytes]]:
        return None

    def build_position_request(self) -> Optional[tuple[int, bytes]]:
        return None

    def handle_can_message(self, msg_id: int, data: bytes):
        pass