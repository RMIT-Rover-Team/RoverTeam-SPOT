# -------------------------
# DUMMY ACTUATOR
# -------------------------
import time

class DummyActuator:
    """
    Software-only actuator.
    Integrates velocity into position locally.
    """

    def __init__(self, name: str):
        self.name = name
        self.velocity = 0.0
        self.position = 0.0
        self._last_time = time.time()

    def set_velocity(self, velocity: float):
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        # integrate previous velocity first
        self.position += self.velocity * dt

        self.velocity = velocity

    async def update(self):
        """
        Called periodically by manager loop to keep integrating
        even if velocity doesn't change.
        """
        now = time.time()
        dt = now - self._last_time
        self._last_time = now
        self.position += self.velocity * dt