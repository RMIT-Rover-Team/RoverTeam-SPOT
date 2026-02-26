# odrive_ramp.py

import struct
import time
from .actuator_base import Actuator


class ODriveActuator(Actuator):
    """
    Minimal ODrive CANSimple velocity-only actuator with automatic arming
    and smooth velocity ramping.
    """

    # CANSimple command IDs
    CMD_SET_AXIS_STATE = 0x07
    CMD_SET_INPUT_VEL = 0x0D
    CMD_CLEAR_ERRORS = 0x18

    AXIS_STATE_IDLE = 1
    AXIS_STATE_CLOSED_LOOP = 8

    def __init__(self, name: str, node_id: int, inverted: bool = False, max_accel: float = 10.0):
        """
        Args:
            name: actuator name
            node_id: CAN node ID
            inverted: flip velocity direction
            max_accel: maximum velocity change per loop (turns/sec^2)
        """
        super().__init__(name=name, motor_id=node_id)

        self.node_id = node_id
        self.inverted = inverted

        self._armed = False
        self._arm_requested = False
        self._last_velocity = 0.0
        self.max_accel = max_accel  # turns/sec per loop
        self._last_time = time.time()
        self._lastAxisState = self.AXIS_STATE_IDLE

    # -------------------------------------------------
    # CAN ID helper
    # -------------------------------------------------
    def _msg_id(self, cmd: int) -> int:
        return (self.node_id << 5) | cmd

    # -------------------------------------------------
    # Arming
    # -------------------------------------------------
    def request_arm(self):
        self._arm_requested = True

    def request_disarm(self):
        self._arm_requested = False
        self._armed = False
        self._last_velocity = 0.0

    def build_axis_state_command(self):
        """
        Send axis state change if needed.
        """
        target_state = (
            self.AXIS_STATE_CLOSED_LOOP
            if self._arm_requested
            else self.AXIS_STATE_IDLE
        )

        if target_state == self._lastAxisState:
            return None  # no change needed
        
        self._lastAxisState = target_state

        payload = struct.pack("<I", target_state)
        return self._msg_id(self.CMD_SET_AXIS_STATE), payload

    # -------------------------------------------------
    # Velocity with ramping
    # -------------------------------------------------
    def build_velocity_command(self):
        if not self._arm_requested:
            # reset velocity when disarmed
            self._last_velocity = 0.0
            return None

        # Compute time since last update
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        # Apply ramp limiting
        target_vel = self.target_velocity
        if self.inverted:
            target_vel *= -1

        delta = target_vel - self._last_velocity
        max_delta = self.max_accel * dt
        if abs(delta) > max_delta:
            delta = max_delta if delta > 0 else -max_delta

        ramped_vel = self._last_velocity + delta
        self._last_velocity = ramped_vel

        # Optional feedforward torque (can tweak)
        torque_ff = 0.0

        payload = struct.pack("<ff", ramped_vel, torque_ff)
        return self._msg_id(self.CMD_SET_INPUT_VEL), payload

    # -------------------------------------------------
    # Not used
    # -------------------------------------------------
    def build_position_command(self):
        return None

    def build_position_request(self):
        return None

    # -------------------------------------------------
    # Handle incoming CAN messages (optional)
    # -------------------------------------------------
    def handle_can_message(self, msg_id: int, data: bytes):
        # Currently ignoring feedback
        pass