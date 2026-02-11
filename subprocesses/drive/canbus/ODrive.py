import can
import struct
import time

# -------------------------
# ODrive CAN Command IDs
# -------------------------
SET_AXIS_STATE = 0x07
SET_INPUT_VEL  = 0x0d
HEARTBEAT      = 0x01
CLOSED_LOOP_STATE = 8

# -------------------------
# Initialize CAN bus
# -------------------------
try:
    bus = can.interface.Bus(channel="can0", bustype="socketcan")
except Exception as e:
    print(f"[ERROR] Failed to open CAN bus 'can0': {e}")
    bus = None

# -------------------------
# Utility: send CAN message safely
# -------------------------
def send_can_message(msg: can.Message, retries: int = 3):
    if bus is None:
        print("[WARN] CAN bus not initialized, cannot send message")
        return False

    for attempt in range(1, retries + 1):
        try:
            bus.send(msg)
            return True
        except can.CanError as e:
            print(f"[WARN] CAN send attempt {attempt} failed: {e}")
            time.sleep(0.05)
    print(f"[ERROR] Failed to send CAN message after {retries} attempts")
    return False

# -------------------------
# Startup ODrive
# -------------------------
def startup(node_id: int):
    """
    Initialize and enable ODrive motor for CAN control.
    Sends multiple heartbeats and sets axis to CLOSED_LOOP_CONTROL.
    """
    if bus is None:
        print("[ERROR] CAN bus not available, cannot start ODrive")
        return

    print(f"[INFO] Starting up ODrive {node_id}...")

    # Heartbeats to exit auto-baud scan
    can_id = (node_id << 5) | HEARTBEAT
    msg = can.Message(arbitration_id=can_id, data=bytes(), is_extended_id=False)
    for i in range(5):
        success = send_can_message(msg)
        if not success:
            print(f"[WARN] Heartbeat {i+1} failed for node {node_id}")
        time.sleep(0.05)  # small delay

    # Set axis state to CLOSED_LOOP_CONTROL
    payload = struct.pack("<I", CLOSED_LOOP_STATE)
    can_id = (node_id << 5) | SET_AXIS_STATE
    msg = can.Message(arbitration_id=can_id, data=payload, is_extended_id=False)
    if send_can_message(msg):
        print(f"[INFO] ODrive {node_id} axis set to CLOSED_LOOP_CONTROL")
    else:
        print(f"[ERROR] Failed to set axis state for ODrive {node_id}")

    print(f"[INFO] Startup sequence complete for ODrive {node_id}")

# -------------------------
# Set motor speed
# -------------------------
def set_speed(node_id: int, speed: float):
    """
    Set target velocity on the ODrive via CAN.
    speed: revolutions per second
    """
    if bus is None:
        print("[ERROR] CAN bus not available, cannot send speed")
        return

    payload = struct.pack("<f", speed)
    can_id = (node_id << 5) | SET_INPUT_VEL
    msg = can.Message(arbitration_id=can_id, data=payload, is_extended_id=False)
    if send_can_message(msg):
        print(f"[INFO] Sent speed {speed:.3f} rev/s to ODrive {node_id}")
    else:
        print(f"[ERROR] Failed to send speed to ODrive {node_id}")