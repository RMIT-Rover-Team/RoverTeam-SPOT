import struct
from .actuator_base import Actuator

class ODriveActuator(Actuator):
    """
    ODrive CANSimple actuator with:
    - automatic arming/disarming
    - direct velocity commands
    - position/velocity telemetry from ODrive broadcasts
    """

    # CANSimple command IDs
    CMD_SET_AXIS_STATE = 0x07
    CMD_SET_INPUT_VEL = 0x0D
    CMD_GET_ENCODER_ESTIMATES = 0x09  # broadcasted automatically by ODrive

    # Axis states
    AXIS_STATE_IDLE = 1
    AXIS_STATE_CLOSED_LOOP = 8

    def __init__(self, name: str, node_id: int, inverted: bool = False):
        super().__init__(name=name, motor_id=node_id)
        self.node_id = node_id
        self.inverted = inverted
        self._armed = False
        self._arm_requested = False
        self._lastAxisState = self.AXIS_STATE_IDLE

    # -------------------------
    # CAN helper
    # -------------------------
    def _msg_id(self, cmd: int) -> int:
        """Build message ID using node ID + command."""
        return (self.node_id << 5) | cmd

    # -------------------------
    # Arming
    # -------------------------
    def request_arm(self):
        self._arm_requested = True

    def request_disarm(self):
        self._arm_requested = False
        self._armed = False

    # -------------------------
    # Axis state
    # -------------------------
    def build_axis_state_command(self):
        target_state = (
            self.AXIS_STATE_CLOSED_LOOP if self._arm_requested else self.AXIS_STATE_IDLE
        )

        if target_state == self._lastAxisState:
            return None

        self._lastAxisState = target_state
        payload = struct.pack("<I", target_state)
        return self._msg_id(self.CMD_SET_AXIS_STATE), payload

    # -------------------------
    # Direct velocity commands
    # -------------------------
    def build_velocity_command(self):
        if not self._arm_requested:
            return None

        target_vel = -self.target_velocity if self.inverted else self.target_velocity
        torque_ff = 0.0  # optional feedforward

        payload = struct.pack("<ff", target_vel, torque_ff)
        return self._msg_id(self.CMD_SET_INPUT_VEL), payload

    # -------------------------
    # Handle incoming CAN broadcasts
    # -------------------------
    def handle_can_message(self, msg_id: int, data: bytes):
        """
        Handle incoming encoder estimate broadcasts.
        Data format: pos (float32) + vel (float32)
        """
        expected_id = self._msg_id(self.CMD_GET_ENCODER_ESTIMATES)
        if msg_id != expected_id:
            return  # ignore unrelated messages

        if len(data) < 8:
            return  # ignore invalid frames

        try:
            pos, vel = struct.unpack("<ff", data[:8])
            self._update_position(pos * 360.0)  # turns → degrees
            self._last_velocity = vel * 360.0
            self.connected = True
        except struct.error as e:
            print(f"[ODriveActuator {self.name}] CAN decode error: {e}")

    # -------------------------
    # Accessors
    # -------------------------
    def get_position(self) -> float:
        return self._position

    def get_velocity(self) -> float:
        return super().get_velocity()