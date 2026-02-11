import can
import struct
import time

# command IDs (from ODrive CANSimple)
SET_AXIS_STATE = 0x07
SET_INPUT_VEL    = 0x0d
HEARTBEAT        = 0x01

bus = can.interface.Bus(channel='can0', bustype='socketcan')

def startup(node_id: int):
    """
    Initialize and enable ODrive motor for CAN control.
    node_id: the integer ID of the ODrive on the CAN bus.
    """
    # Heartbeat: let ODrive exit auto-baud scan (send at ~10Hz for a bit)
    can_id = (node_id << 5) | HEARTBEAT
    msg = can.Message(arbitration_id=can_id, data=bytes(), is_extended_id=False)
    for _ in range(5):  # send 5 heartbeats quick
        bus.send(msg)

    # Request closed loop control
    # CLOSED_LOOP_CONTROL state = 8 (uint32)
    payload = struct.pack("<I", 8)
    can_id = (node_id << 5) | SET_AXIS_STATE
    msg = can.Message(arbitration_id=can_id, data=payload, is_extended_id=False)
    bus.send(msg)

    print(f"Startup complete for ODrive {node_id}")

def set_speed(node_id: int, speed: float):
    """
    Set target velocity on the given ODrive node via CAN.
    speed: in revolutions per second (rev/s)
    """
    # Pack as float32 (little endian)
    payload = struct.pack("<f", speed)

    # The CAN ID for "Set_Input_Vel" (velocity command)
    can_id = (node_id << 5) | SET_INPUT_VEL

    msg = can.Message(arbitration_id=can_id, data=payload, is_extended_id=False)
    bus.send(msg)
    print(f"Sent speed {speed:.3f} to ODrive {node_id}")

startup(1)