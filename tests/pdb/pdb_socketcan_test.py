# import struct
# import time

# import can
# import pytest

# from subprocesses.pdb.telemetry.telemetry import PDBTelemetryManager


# class SocketCANClient:
#     def __init__(self, channel="vcan0"):
#         self.bus = can.Bus(channel=channel, interface="socketcan")
#         self.subscribers = {}
#         self.notifier = can.Notifier(self.bus, [self._on_msg])

#     def subscribe(self, msg_id, callback):
#         self.subscribers[msg_id] = callback

#     def _on_msg(self, msg):
#         # We need to shift the ID to get the 'Board ID' part your manager expects
#         # Because your code subscribes to Board IDs, not full 12-bit IDs
#         board_id = (msg.arbitration_id >> 6) & 0x3F
#         if board_id in self.subscribers:
#             self.subscribers[board_id](msg.arbitration_id, msg.data)

#     def send_raw(self, arb_id, data):
#         self.bus.send(can.Message(arbitration_id=arb_id, data=data))


# @pytest.fixture
# def vcan_manager():
#     client = SocketCANClient("vcan0")
#     manager = PDBTelemetryManager(client)

#     # This assumes your 'register' method correctly binds to the client
#     # If SWITCH_ID is 0x0A, the client should listen for messages starting with 0x0A...
#     manager.register_all()

#     yield manager, client
#     client.notifier.stop()
#     client.bus.shutdown()


# def test_vcan_transmission(vcan_manager):
#     manager, client = vcan_manager
#     try:
#         arb_id = (0x06 << 6) | 0x01  # Board 0x06 (Buck1), Source 0x01 -> Arb ID 0x181
#         print(arb_id)
#         byte0 = 0x72  # Command 7, Attribute 2 (power)
#         # byte1 = 0x00  # Channel 0
#         power_value = 45.75

#         payload = bytearray(8)
#         payload[0] = byte0
#         struct.pack_into(">f", payload, 2, power_value)

#         client.send_raw(arb_id, bytes(payload))

#         # 2. Give the background thread a moment to process
#         time.sleep(0.05)

#         print(manager.buck1)
#         print(manager.buck2)
#         print(manager.bms)
#         print(manager.switch)
#         # 3. Verify
#     except Exception as e:
#         print(f"Error: {e}")
#     assert manager.buck1[0].power == pytest.approx(45.75)

# Fix later, cause gotta make it so ZMQ Can subprocess is up to pass messages into the testcase
