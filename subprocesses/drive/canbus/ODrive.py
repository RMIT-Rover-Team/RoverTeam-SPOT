import struct
import time
import threading
import can

from .canbus import CANBus

# -------------------------
# ODrive CANSimple Command IDs
# -------------------------
HEARTBEAT       = 0x01
SET_AXIS_STATE  = 0x07
SET_INPUT_VEL   = 0x0d

AXIS_STATE_IDLE         = 1
AXIS_STATE_CLOSED_LOOP  = 8

# -------------------------
# Error codes
# -------------------------
ERR_CODES = {
    0x1: "INITIALIZING",
    0x2: "SYSTEM_LEVEL",
    0x4: "TIMING_ERROR",
    0x8: "MISSING_ESTIMATE",
    0x10: "BAD_CONFIG",
    0x20: "DRV_FAULT",
    0x40: "MISSING_INPUT",
    0x100: "DC_BUS_OVER_VOLTAGE",
    0x200: "DC_BUS_UNDER_VOLTAGE",
    0x400: "DC_BUS_OVER_CURRENT",
    0x800: "DC_BUS_OVER_REGEN_CURRENT",
    0x1000: "CURRENT_LIMIT_VIOLATION",
    0x2000: "MOTOR_OVER_TEMP",
    0x4000: "INVERTER_OVER_TEMP",
    0x8000: "VELOCITY_LIMIT_VIOLATION",
    0x10000: "POSITION_LIMIT_VIOLATION",
    0x1000000: "WATCHDOG_TIMER_EXPIRED",
    0x2000000: "ESTOP_REQUESTED",
    0x4000000: "SPINOUT_DETECTED",
    0x8000000: "BRAKE_RESISTOR_DISARMED",
    0x10000000: "THERMISTOR_DISCONNECTED",
    0x40000000: "CALIBRATION_ERROR"
}

# -------------------------
# Error decode helper
# -------------------------
def decode_errors(error_value: int) -> list[str]:
    errors = [
        name for bit, name in ERR_CODES.items()
        if error_value & bit
    ]
    return errors if errors else ["NO_ERROR"]

# -------------------------
# ODrive class
# -------------------------
class ODrive:
    def __init__(self, node_id: int, canbus: CANBus, inverted: bool = False):
        self.node_id = node_id
        self.inverted = inverted
        self.canbus = canbus
        self._pending_arm = False
        self._pending_disarm = False
        self.is_armed = False

        self.last_heartbeat_time = None
        self.state = None
        self.error_code = 0
        self.error_string = "NO_ERROR"
        self.traj_done = None

        self.encoder_position = 0.0
        self.encoder_velocity = 0.0
        self.last_encoder_time = None

        # Start a background heartbeat listener
        self._listener_thread = threading.Thread(target=self._heartbeat_listener, daemon=True)
        self._listener_thread.start()

        # Start encoder listener thread
        self._encoder_thread = threading.Thread(target=self._encoder_listener, daemon=True)
        self._encoder_thread.start()

    # -------------------------
    # Utility
    # -------------------------
    def _msg_id(self, cmd):
        return (self.node_id << 5) | cmd

    # -------------------------
    # Arm / Disarm
    # -------------------------
    def arm(self):
        if self.is_armed or self._pending_arm:
            return
        self._pending_arm = True
        self._pending_disarm = False

        # First clear any active errors
        self.clear_errors(identify=0)

        # Attempt to arm the device
        self._set_axis_state(AXIS_STATE_CLOSED_LOOP)
        print(f"[INFO] Arm requested for ODrive {self.node_id}")

    def disarm(self):
        if not self.is_armed or self._pending_disarm:
            return
        self._pending_disarm = True
        self._pending_arm = False
        self._set_axis_state(AXIS_STATE_IDLE)
        print(f"[INFO] Disarm requested for ODrive {self.node_id}")

    # -------------------------
    # heartbeat and encoder listeners
    # -------------------------
    def _heartbeat_listener(self):
        while True:
            msg = self.canbus.recv(timeout=0.1)
            if not msg or msg.arbitration_id != self._msg_id(HEARTBEAT):
                continue
            try:
                error, state, result, traj_done = struct.unpack("<IBBB", msg.data[:7])
            except Exception:
                continue

            self.last_heartbeat_time = time.time()
            self.state = state
            self.error_code = error
            self.error_string = ", ".join(decode_errors(error))
            self.traj_done = traj_done

            # Update is_armed based on actual state
            if self.state == AXIS_STATE_CLOSED_LOOP:
                self.is_armed = True
                self._pending_arm = False
            else:
                self.is_armed = False
                self._pending_disarm = False

    def _encoder_listener(self):
        while True:
            msg = self.canbus.recv(timeout=0.01)  # encoder messages are fast
            if not msg:
                continue

            # Encoder estimate messages have ID = (node_id << 5) | 0x02
            if msg.arbitration_id != self._msg_id(0x02):
                continue

            try:
                # Encoder count: int32
                # Position estimate: float32
                pos, vel = struct.unpack("<fi", msg.data[:8])
            except Exception:
                continue

            self.encoder_position = pos
            self.encoder_velocity = vel
            self.last_encoder_time = time.time()

    # -------------------------
    # Velocity
    # -------------------------
    def set_velocity(self, velocity: float, torque_ff: float = 0.0):
        if self.inverted:
            velocity *= -1

        payload = struct.pack("<ff", velocity, torque_ff)
        msg = can.Message(
            arbitration_id=self._msg_id(SET_INPUT_VEL),
            data=payload,
            is_extended_id=False
        )

        if self.canbus.send(msg):
            #print(f"[INFO] Velocity {velocity:.3f} sent to {self.node_id}")
            return True

        #print(f"[ERROR] Failed to send velocity to {self.node_id}")
        return False

    # -------------------------
    # Axis state
    # -------------------------
    def _set_axis_state(self, state: int) -> bool:
        payload = struct.pack("<I", state)
        msg = can.Message(
            arbitration_id=self._msg_id(SET_AXIS_STATE),
            data=payload,
            is_extended_id=False
        )
        return self.canbus.send(msg)

    def _wait_for_state(self, target_state: int, timeout: float = 3.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self.state == target_state:
                return True
            time.sleep(0.01)
        return False
    
    # -------------------------
    # Clear Errors
    # -------------------------
    def clear_errors(self, identify: int = 0) -> bool:
        """
        Sends the ODrive Clear_Errors command over CAN.
        `identify`: If nonzero, the ODrive may blink an LED after errors are cleared.
        """
        payload = struct.pack("<B", identify)
        msg = can.Message(
            arbitration_id=self._msg_id(0x18),  # Clear_Errors cmd
            data=payload,
            is_extended_id=False
        )
        sent = self.canbus.send(msg)
        if sent:
            print(f"[INFO] Sent Clear_Errors to ODrive {self.node_id}")
        else:
            print(f"[WARN] Failed to send Clear_Errors to ODrive {self.node_id}")
        return sent