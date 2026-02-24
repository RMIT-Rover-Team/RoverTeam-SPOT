from abc import ABC, abstractmethod
from typing import Optional
import time
from collections import deque

class Actuator(ABC):
    def __init__(self, name: str, motor_id: Optional[int]):
        self.name = name
        self.motor_id = motor_id
        self.target_mode: int = 0  # 0 for velocity, 1 for position
        self.target_velocity: float = 0.0
        self.target_position: float = 0.0
        self._position: float = 0.0
        self.connected: bool = False

        # For velocity estimation
        self._history = deque(maxlen=5)  # store (timestamp, position)

    def set_velocity(self, vel: float):
        self.target_mode = 0
        self.target_velocity = vel

    def set_position(self, pos: float):
        self.target_mode = 1
        self.target_position = pos

    def get_position(self) -> float:
        """Return current position (encoder or dummy)."""
        return self._position

    def get_velocity(self) -> float:
        """Return estimated velocity using last few position samples."""
        if len(self._history) < 2:
            return 0.0
        dt = self._history[-1][0] - self._history[0][0]
        dp = self._history[-1][1] - self._history[0][1]
        return dp / dt if dt > 0 else 0.0

    def _update_position(self, pos: float):
        """Internal: update position and history."""
        self._position = pos
        self._history.append((time.time(), pos))

    @abstractmethod
    def build_velocity_command(self) -> Optional[tuple[int, bytes]]:
        pass

    @abstractmethod
    def build_position_command(self) -> Optional[tuple[int, bytes]]:
        pass

    @abstractmethod
    def build_position_request(self) -> Optional[tuple[int, bytes]]:
        pass

    @abstractmethod
    def handle_can_message(self, msg_id: int, data: bytes):
        pass