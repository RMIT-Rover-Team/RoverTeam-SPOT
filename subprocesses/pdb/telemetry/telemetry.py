from dataclasses import dataclass
from typing import List, Optional, Union
import string
import struct


@dataclass
class ChannelMetrics:
    voltage: float = 0.0
    current: float = 0.0
    power: float = 0.0
    temp: float = 0.0


class PDBTelemetryManager:
    SWITCH_ID = 0xA
    BUCK1_ID = 0x06
    BUCK2_ID = 0x07
    BMS_ID = 0x08

    def __init__(self, can_client):
        self.can = can_client

        self.switch: List[ChannelMetrics] = [ChannelMetrics() for _ in range(8)]

        self.buck1: List[ChannelMetrics] = [ChannelMetrics() for _ in range(2)]
        self.buck2: List[ChannelMetrics] = [ChannelMetrics() for _ in range(2)]

        self.bms: List[float] = [0.0] * 12

    def register_all(self):
        board_ids = [self.SWITCH_ID, self.BUCK1_ID, self.BUCK2_ID, self.BMS_ID]
        for b_id in board_ids:
            self.can.subscribe(
                b_id, lambda data, mid=b_id: self.handle_can_message(mid, data)
            )

    def handle_can_message(self, msg_id: int, data: bytes):
        destination_id, source_id = self.convert_arbitration_id(msg_id)
        command_id = (data[0] >> 4) & 0x0F
        attribute_id = data[0] & 0x0F
        channel_id = (data[1] >> 4) & 0x0F

        if command_id != 0x7:
            print("Not broadcast command")
            return

        board = self.get_board(destination_id)
        attribute_name = self.get_attribute(attribute_id)
        value = struct.unpack_from(">f", data, 3)[0]

        if board is None:
            return

        if destination_id == self.BMS_ID:  # BMS
            if channel_id < len(self.bms):
                self.bms[channel_id] = value
        else:  # Channel Metrics
            if channel_id < len(board) and attribute_name:
                setattr(board[channel_id], attribute_name, value)

    # Helper functions
    def get_board(
        self, board_id: int
    ) -> Optional[Union[List[ChannelMetrics], List[float]]]:
        match board_id:
            case self.SWITCH_ID:
                return self.switch
            case self.BUCK1_ID:
                return self.buck1
            case self.BUCK2_ID:
                return self.buck2
            case self.BMS_ID:
                return self.bms
            case _:
                # Handle invalid id
                print(f"Error: Board id {board_id} out of range.")
                return None

    @staticmethod
    def get_attribute(attribute: int) -> str:
        match attribute:
            case 0:
                return "current"
            case 1:
                return "voltage"
            case 2:
                return "power"
            case 3:
                return "temp"

    @staticmethod
    def convert_arbitration_id(arbitration_id: int) -> tuple[int, int]:
        destination_id = (arbitration_id >> 6) & 0x3F
        source_id = arbitration_id & 0x3F

        return destination_id, source_id
