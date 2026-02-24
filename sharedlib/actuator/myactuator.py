from .actuator_base import Actuator


class MyActuator(Actuator):
    BROADCAST_ID = 0x280

    def build_velocity_command(self):
        if self.motor_id is None:
            return None

        speed_int32 = int(self.target_velocity / 0.01)

        data = bytearray(8)
        data[0] = 0xA2
        data[1] = 0xFF
        data[2] = 0x00
        data[3] = 0x00
        data[4:8] = speed_int32.to_bytes(4, "little", signed=True)

        return self.motor_id, bytes(data)

    def build_position_request(self):
        # Broadcast version
        return self.BROADCAST_ID, bytes([0x92] + [0] * 7)

    def handle_can_message(self, msg_id: int, data: bytes):
        if len(data) < 8 or data[0] != 0x92:
            return

        motor_angle_int = int.from_bytes(data[4:8], "little", signed=True)
        self.position = motor_angle_int * 0.01
        self.connected = True