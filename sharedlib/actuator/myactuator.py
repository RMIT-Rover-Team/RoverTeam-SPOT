from .actuator_base import Actuator

class MyActuator(Actuator):
    BROADCAST_ID = 0x280

    CMD_SET_VELOCITY = 0xA2
    CMD_SET_POSITION = 0xA4
    CMD_REQUEST_POSITION = 0x92

    def build_velocity_command(self):
        if self.motor_id is None:
            return None

        speed_int32 = int(self.target_velocity / 0.01)

        data = bytearray(8)
        data[0] = self.CMD_SET_VELOCITY
        data[1] = 0xFF
        data[2] = 0x00
        data[3] = 0x00
        data[4:8] = speed_int32.to_bytes(4, "little", signed=True)

        return self.motor_id, bytes(data)

    def build_position_command(self):
        if self.motor_id is None:
            return None

        # Convert target position to 0.01 deg/LSB
        angle_int32 = int(self.target_position / 0.01)

        # Limit maximum speed in deg/s (uint16)
        speed_uint16 = int(500)  # max speed, adjust if needed

        data = bytearray(8)
        data[0] = 0xA4  # Force control command
        data[1] = 0x00
        data[2:4] = speed_uint16.to_bytes(2, "little", signed=False)
        data[4:8] = angle_int32.to_bytes(4, "little", signed=True)

        return self.motor_id, bytes(data)

    def build_position_request(self):
        # Broadcast request for encoder value
        return self.BROADCAST_ID, bytes([self.CMD_REQUEST_POSITION] + [0] * 7)

    def handle_can_message(self, msg_id: int, data: bytes):
        # Handle position response from motor
        if len(data) < 8 or data[0] != self.CMD_REQUEST_POSITION:
            return

        motor_angle_int = int.from_bytes(data[4:8], "little", signed=True)
        self._update_position(motor_angle_int * 0.01)
        self.connected = True

    # -------------------------
    # Real get_position / get_velocity
    # -------------------------
    def get_position(self) -> float:
        """
        Return the latest position in degrees.
        Updated asynchronously by handle_can_message.
        """
        return self._position

    def get_velocity(self) -> float:
        """
        Estimate velocity using recent position history.
        """
        return super().get_velocity()