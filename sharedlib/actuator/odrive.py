# odrive.py

import struct
from .actuator_base import Actuator


class ODriveActuator(Actuator):
    """
    Minimal ODrive CANSimple velocity-only actuator.
    Works with ActuatorManager.
    """

    # CANSimple command IDs
    CMD_SET_AXIS_STATE = 0x07
    CMD_SET_INPUT_VEL = 0x0D
    CMD_CLEAR_ERRORS = 0x18

    AXIS_STATE_IDLE = 1
    AXIS_STATE_CLOSED_LOOP = 8

    def __init__(self, name: str, node_id: int, inverted: bool = False):
        super().__init__(name=name, motor_id=node_id)

        self.node_id = node_id
        self.inverted = inverted

        self._armed = False
        self._arm_requested = False

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

    def build_axis_state_command(self):
        """
        Send axis state change if needed.
        """
        target_state = (
            self.AXIS_STATE_CLOSED_LOOP
            if self._arm_requested
            else self.AXIS_STATE_IDLE
        )

        payload = struct.pack("<I", target_state)
        return self._msg_id(self.CMD_SET_AXIS_STATE), payload

    # -------------------------------------------------
    # Velocity
    # -------------------------------------------------
    def build_velocity_command(self):
        if not self._arm_requested:
            return None

        velocity = self.target_velocity
        if self.inverted:
            velocity *= -1

        payload = struct.pack("<ff", velocity, 0.0)

        return self._msg_id(self.CMD_SET_INPUT_VEL), payload

    # -------------------------------------------------
    # Not used for now
    # -------------------------------------------------
    def build_position_command(self):
        return None

    def build_position_request(self):
        return None

    def handle_can_message(self, msg_id: int, data: bytes):
        """
        For now we ignore heartbeat / encoder feedback.
        Can extend later.
        """
        pass