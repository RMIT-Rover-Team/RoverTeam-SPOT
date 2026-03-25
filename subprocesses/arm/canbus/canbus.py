import can
import time
import subprocess

# -------------------------
# Create CAN bus interface
# -------------------------

class CANBus:
    def __init__(self, channel="can0", bustype="socketcan"):
        try:
            # Just incase we try to load it up
            subprocess.run(["sudo", "ip", "link", "set", "can0", "down"])
            subprocess.run(["sudo", "ip", "link", "set", "can0", "up", "type", "can", "bitrate", "125000"])

            self.bus = can.interface.Bus(
                channel=channel,
                bustype=bustype
            )
            print(f"[INFO] CAN bus opened on {channel}")
        except Exception as e:
            print(f"[ERROR] Could not open CAN bus: {e}")
            self.bus = None

    def available(self) -> bool:
        return self.bus is not None

    # -------------------------
    # Send CAN message utility
    # -------------------------

    def send(self, msg: can.Message, retries=3, delay=0.05) -> bool:
        if not self.available():
            print("[ERROR] CAN bus not initialized")
            return False

        for attempt in range(1, retries + 1):
            try:
                self.bus.send(msg)
                return True
            except can.CanError as e:
                print(f"[WARN] CAN send attempt {attempt} failed: {e}")
                time.sleep(delay)

        print("[ERROR] CAN message failed after retries")
        return False

    # -------------------------
    # Receive helper
    # -------------------------

    def recv(self, timeout=0.1):
        if not self.available():
            return None
        return self.bus.recv(timeout=timeout)