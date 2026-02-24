from abc import ABC, abstractmethod
from typing import Optional


class Actuator(ABC):
    def __init__(self, name: str, motor_id: Optional[int]):
        self.name = name
        self.motor_id = motor_id
        self.target_velocity: float = 0.0
        self.position: float = 0.0
        self.connected: bool = False

    def set_velocity(self, vel: float):
        self.target_velocity = vel

    @abstractmethod
    def build_velocity_command(self) -> Optional[tuple[int, bytes]]:
        """Return (can_id, data) or None"""

    @abstractmethod
    def build_position_request(self) -> Optional[tuple[int, bytes]]:
        """Return (can_id, data) or None"""

    @abstractmethod
    def handle_can_message(self, msg_id: int, data: bytes):
        pass