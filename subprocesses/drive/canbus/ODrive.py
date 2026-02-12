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

AXIS_STATE_IDLE         = 0
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
        self.is_armed = False

        self.last_heartbeat_time = None
        self.state = None
        self.error_code = 0
        self.error_string = "NO_ERROR"
        self.traj_done = None

        # Start a background heartbeat listener
        self._listener_thread = threading.Thread(target=self._heartbeat_listener, daemon=True)
        self._listener_thread.start()

    # -------------------------
    # Utility
    # -------------------------
    def _msg_id(self, cmd):
        return (self.node_id << 5) | cmd

    # -------------------------
    # Heartbeat listener
    # -------------------------
    def _heartbeat_listener(self):
        while True:
            try:
                msg = self.canbus.recv(timeout=0.1)
                if msg and msg.arbitration_id == self._msg_id(HEARTBEAT):
                    self._update_from_heartbeat(msg)
            except Exception:
                continue

    def _update_from_heartbeat(self, msg: can.Message):
        try:
            error, state, result, traj_done = struct.unpack("<IBBB", msg.data[:7])
        except Exception:
            return

        self.last_heartbeat_time = time.time()
        self.state = state
        self.error_code = error
        self.error_string = ", ".join(decode_errors(error))
        self.traj_done = traj_done

    # -------------------------
    # Arm / Disarm
    # -------------------------
    def arm(self, wait=True):
        if self.is_armed:
            return True

        print(f"[INFO] Arming ODrive {self.node_id}...")
        self._set_axis_state(AXIS_STATE_CLOSED_LOOP)
        if wait and not self._wait_for_state(AXIS_STATE_CLOSED_LOOP):
            print(f"[WARN] Failed to arm {self.node_id}")
            return False

        self.is_armed = True
        print(f"[INFO] ODrive {self.node_id} armed")
        return True

    def disarm(self):
        if not self.is_armed:
            return True

        print(f"[INFO] Disarming ODrive {self.node_id}...")
        self._set_axis_state(AXIS_STATE_IDLE)
        if not self._wait_for_state(AXIS_STATE_IDLE):
            print(f"[WARN] Failed to disarm {self.node_id}")
            return False

        self.is_armed = False
        print(f"[INFO] ODrive {self.node_id} disarmed")
        return True

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
            print(f"[INFO] Velocity {velocity:.3f} sent to {self.node_id}")
            return True

        print(f"[ERROR] Failed to send velocity to {self.node_id}")
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