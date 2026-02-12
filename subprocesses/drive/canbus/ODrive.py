import struct
import time
import can

from .canbus import CANBus

# -------------------------
# ODrive CANSimple Command IDs
# -------------------------

HEARTBEAT       = 0x01
SET_AXIS_STATE = 0x07
SET_INPUT_VEL  = 0x0d

AXIS_STATE_CLOSED_LOOP = 8

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
    def __init__(self, node_id: int, canbus: CANBus):
        self.node_id = node_id
        self.canbus = canbus
        self.is_armed = False

    def _msg_id(self, cmd):
        return (self.node_id << 5) | cmd

    # -------------------------
    # Wait for Heartbeat
    # -------------------------

    def wait_for_heartbeat(self, timeout=2.0) -> bool:
        start = time.time()

        while time.time() - start < timeout:
            msg = self.canbus.recv(timeout=0.1)
            if not msg:
                continue

            if msg.arbitration_id != self._msg_id(HEARTBEAT):
                continue

            try:
                error, state, result, traj_done = struct.unpack("<IBBB", msg.data[:7])
                error_string = ", ".join(decode_errors(error))
                print(
                    f"[INFO] Heartbeat from {self.node_id}: "
                    f"state={state}, error={error} [{error_string}]"
                )
                return True
            except Exception:
                print(f"[WARN] Heartbeat format unexpected on node {self.node_id}")
                return False

        print(f"[WARN] No heartbeat received from ODrive {self.node_id}")
        return False

    # -------------------------
    # Arm the drive
    # -------------------------

    def arm(self, wait=True):
        if self.is_armed:
            return True   # already running — do nothing

        print(f"[INFO] Arming ODrive {self.node_id}...")

        beacon_msg = can.Message(
            arbitration_id=self._msg_id(HEARTBEAT),
            data=b"",
            is_extended_id=False
        )

        for _ in range(5):
            self.canbus.send(beacon_msg)
            time.sleep(0.05)

        payload = struct.pack("<I", AXIS_STATE_CLOSED_LOOP)

        state_msg = can.Message(
            arbitration_id=self._msg_id(SET_AXIS_STATE),
            data=payload,
            is_extended_id=False
        )

        self.canbus.send(state_msg)

        # confirm via heartbeat
        start = time.time()
        while time.time() - start < 3.0:
            if self.wait_for_heartbeat(timeout=0.3):
                self.is_armed = True
                print(f"[INFO] ODrive {self.node_id} armed")
                return True

        print(f"[WARN] ODrive {self.node_id} failed to arm")
        return False

    # -------------------------
    # Velocity command
    # -------------------------

    def set_velocity(self, velocity: float, torque_ff: float = 0.0):
        payload = struct.pack("<ff", velocity, torque_ff)

        vel_msg = can.Message(
            arbitration_id=self._msg_id(SET_INPUT_VEL),
            data=payload,
            is_extended_id=False
        )

        if self.canbus.send(vel_msg):
            print(f"[INFO] Velocity {velocity:.3f} sent to {self.node_id}")
            return True

        print(f"[ERROR] Failed to send velocity to {self.node_id}")
        return False