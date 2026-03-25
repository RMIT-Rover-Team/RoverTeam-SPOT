import time
from typing import Optional
from .actuator_base import Actuator

class DummyActuator(Actuator):
    def __init__(self, name: str):
        super().__init__(name, motor_id=None)
        self._last_time = time.time()

    def set_velocity(self, velocity: float):
        now = time.time()
        dt = now - self._last_time
        self._last_time = now
        self._update_position(self._position + self.target_velocity * dt)
        self.target_velocity = velocity
        self.target_mode = 0

    def set_position(self, position: float):
        self._update_position(position)
        self.target_position = position
        self.target_mode = 1

    # -------------------------
    # CAN interface returns None
    # -------------------------
    def build_velocity_command(self) -> Optional[tuple[int, bytes]]:
        return None

    def build_position_command(self) -> Optional[tuple[int, bytes]]:
        return None

    def build_position_request(self) -> Optional[tuple[int, bytes]]:
        now = time.time()
        dt = now - self._last_time
        self._last_time = now
        self._update_position(self._position + self.target_velocity * dt)
        return None

    def handle_can_message(self, msg_id: int, data: bytes):
        pass