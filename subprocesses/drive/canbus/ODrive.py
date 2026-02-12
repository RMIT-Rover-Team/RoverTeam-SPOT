import can
import struct
import time

# -------------------------
# ODrive CANSimple Command IDs
# -------------------------
HEARTBEAT      = 0x01
SET_AXIS_STATE = 0x07
SET_INPUT_VEL  = 0x0d

# Axis State Values
AXIS_STATE_CLOSED_LOOP = 8

# Error codes
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

def decode_errors(error_value: int, err_codes: dict = ERR_CODES) -> list[str]:
    e = [
        name
        for bit, name in err_codes.items()
        if error_value & bit
    ]
    if len(e) < 1:
        return ["NO_ERROR"]
    else:
        return e

# -------------------------
# Create CAN bus interface
# -------------------------
try:
    bus = can.interface.Bus(channel="can0", bustype="socketcan")
except Exception as e:
    print(f"[ERROR] Could not open CAN bus: {e}")
    bus = None

# -------------------------
# Send CAN message utility
# -------------------------
def send_can(msg: can.Message, retries=3, delay=0.05) -> bool:
    """Send a CAN message with retries and logging."""
    if bus is None:
        print("[ERROR] CAN bus not initialized")
        return False
    for attempt in range(1, retries + 1):
        try:
            bus.send(msg)
            return True
        except can.CanError as e:
            print(f"[WARN] CAN send attempt {attempt} failed: {e}")
            time.sleep(delay)
    print("[ERROR] CAN message failed after retries")
    return False

# -------------------------
# Wait for Heartbeat
# -------------------------
def wait_for_heartbeat(node_id: int, timeout=2.0) -> bool:
    """
    Wait for a heartbeat from the given node.
    Returns True if a heartbeat arrives before timeout.
    """
    if bus is None:
        return False

    target_id = (node_id << 5) | HEARTBEAT
    start = time.time()
    while time.time() - start < timeout:
        msg = bus.recv(timeout=0.1)
        if msg and msg.arbitration_id == target_id:
            # msg.data contains: error (uint32), state (uint8), result (uint8), traj_done (uint8)
            try:
                error, state, result, traj_done = struct.unpack("<IBBB", msg.data[:7])
                errorString = ", ".join(decode_errors(error))
                print(f"[INFO] Heartbeat from {node_id}: state={state}, error={errorString}")
            except Exception:
                print(f"[WARN] Heartbeat format unexpected on node {node_id}")
            return True
    print(f"[WARN] No heartbeat received from ODrive {node_id}")
    return False

# -------------------------
# Startup Sequence
# -------------------------
def startup(node_id: int, wait=True):
    """
    Signal ODrive to exit auto-baud scan and enter CLOSED_LOOP_CONTROL.
    If `wait` is True, the function waits for confirmation via heartbeat.
    """
    if bus is None:
        print("[ERROR] CAN bus not available")
        return False

    print(f"[INFO] Starting ODrive {node_id}...")

    # Send a few quick heartbeat-like messages so the ODrive exits auto-baud scan. :contentReference[oaicite:2]{index=2}
    beacon_id = (node_id << 5) | HEARTBEAT
    beacon_msg = can.Message(arbitration_id=beacon_id, data=b"", is_extended_id=False)
    for _ in range(5):
        send_can(beacon_msg)
        time.sleep(0.05)

    # Request axis enter CLOSED_LOOP_CONTROL
    payload = struct.pack("<I", AXIS_STATE_CLOSED_LOOP)
    cmd_id = (node_id << 5) | SET_AXIS_STATE
    state_msg = can.Message(arbitration_id=cmd_id, data=payload, is_extended_id=False)
    send_can(state_msg)

    print(f"[INFO] Sent CLOSED_LOOP_CONTROL to ODrive {node_id}")

    if wait:
        # Wait for confirmation via heartbeat state update
        # Heartbeat state == 8 means closed-loop. :contentReference[oaicite:3]{index=3}
        start = time.time()
        while time.time() - start < 3.0:
            if wait_for_heartbeat(node_id, timeout=0.3):
                return True
        print(f"[WARN] ODrive {node_id} did not confirm CLOSED_LOOP_CONTROL")
        return False

    return True

# -------------------------
# Set Velocity (Closed Loop)
# -------------------------
def set_velocity(node_id: int, velocity: float, torque_feedforward: float = 0.0):
    """
    Sends a Set_Input_Vel command (velocity + optional torque feedforward). 
    velocity: target in turns/sec
    torque_feedforward: typically 0.0 for velocity control
    """
    if bus is None:
        print("[ERROR] CAN bus not available")
        return False

    # ODrive expects two floats: velocity first, then torque feedforward
    payload = struct.pack("<ff", velocity, torque_feedforward)
    msg_id = (node_id << 5) | SET_INPUT_VEL
    vel_msg = can.Message(arbitration_id=msg_id, data=payload, is_extended_id=False)

    success = send_can(vel_msg)
    if success:
        print(f"[INFO] Velocity {velocity:.3f} cmd sent to ODrive {node_id}")
    else:
        print(f"[ERROR] Failed to send velocity cmd to {node_id}")
    return success

# -------------------------
# Example
# -------------------------
if __name__ == "__main__":
    if startup(0):
        time.sleep(0.1)
        set_velocity(0, 1.0)
        time.sleep(2.0)
        set_velocity(0, 0.0)
    else:
        print("[ERROR] Startup failed for node 0")