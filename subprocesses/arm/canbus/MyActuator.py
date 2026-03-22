import struct
import time
import threading
import can

from .canbus import CANBus


# -------------------------
# Command IDs
# -------------------------
CMD_READ_MULTI_TURN_ANGLE = 0x92
CMD_ABSOLUTE_POSITION     = 0xA4


# -------------------------
# MyActuator Class
# -------------------------
class MyActuator:
    def __init__(self, motor_id: int, canbus: CANBus, ws_send=None):
        """
        motor_id: actuator CAN ID (base ID added to 0x140 / 0x240)
        canbus: shared CANBus instance
        """
        self.motor_id = motor_id
        self.canbus = canbus
        self.ws_send = ws_send

        # State
        self.position_deg = 0.0
        self.raw_position = 0
        self.last_position_time = None

        self._position_lock = threading.Lock()

        # Start listener thread
        self._listener_thread = threading.Thread(
            target=self._listener,
            daemon=True
        )
        self._listener_thread.start()
    
    def set_ws_send(self, ws_send):
        self.ws_send = ws_send

    # -------------------------
    # CAN ID helpers
    # -------------------------
    def _tx_id(self):
        return 0x140 + self.motor_id

    def _rx_id(self):
        return 0x240 + self.motor_id

    # -------------------------
    # WebSocket push
    # -------------------------
    def _send_ws(self):
        if not self.ws_send:
            return

        data = {
            "motor_id": self.motor_id,
            "position_deg": self.position_deg,
            "raw_position": self.raw_position,
            "last_update": self.last_position_time,
            "connected": self.last_position_time is not None,
        }

        self.ws_send({
            "type": "arm",
            "motor_id": self.motor_id,
            "data": data
        })

    # -------------------------
    # Listener
    # -------------------------
    def _listener(self):
        while True:
            msg = self.canbus.recv(timeout=0.1)
            if not msg:
                continue

            if msg.arbitration_id != self._rx_id():
                continue

            if len(msg.data) != 8:
                continue

            cmd = msg.data[0]

            # Position reply
            if cmd == CMD_READ_MULTI_TURN_ANGLE:
                try:
                    # int32 at DATA[4..7]
                    raw_angle = struct.unpack("<i", msg.data[4:8])[0]
                except Exception:
                    continue

                with self._position_lock:
                    self.raw_position = raw_angle
                    self.position_deg = raw_angle * 0.01  # 0.01° per LSB
                    self.last_position_time = time.time()

                self._send_ws()

    # -------------------------
    # Get Position
    # -------------------------
    def get_position(self) -> bool:
        """
        Sends read multi-turn angle command (0x92).
        Position will be updated asynchronously via listener.
        """
        data = bytearray(8)
        data[0] = CMD_READ_MULTI_TURN_ANGLE

        msg = can.Message(
            arbitration_id=self._tx_id(),
            data=data,
            is_extended_id=False
        )

        return self.canbus.send(msg)

    def get_position_blocking(self, timeout: float = 1.0):
        """
        Sends request and waits for updated position.
        """
        self.get_position()
        start = time.time()

        last_time = self.last_position_time

        while time.time() - start < timeout:
            if self.last_position_time != last_time:
                return self.position_deg
            time.sleep(0.01)

        return None

    # -------------------------
    # Set Absolute Position
    # -------------------------
    def set_position(self, angle_deg: float, max_speed_dps: int = 0) -> bool:
        """
        angle_deg: target position in degrees (multi-turn)
        max_speed_dps: max speed in deg/sec (1 dps per LSB)
                       0 = unlimited (PI output only)
        """

        # Convert units
        angle_control = int(angle_deg * 100.0)  # 0.01°/LSB
        max_speed = int(max_speed_dps)

        data = bytearray(8)
        data[0] = CMD_ABSOLUTE_POSITION
        data[1] = 0x00
        data[2:4] = struct.pack("<H", max_speed)
        data[4:8] = struct.pack("<i", angle_control)

        msg = can.Message(
            arbitration_id=self._tx_id(),
            data=data,
            is_extended_id=False
        )

        return self.canbus.send(msg)