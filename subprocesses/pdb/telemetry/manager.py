import dataclasses
import logging
import struct
from typing import List, Optional, Union

from sharedlib.canbus.client import CANClient

from ..models import AttributeID, BoardID, ChannelMetrics, CommandID


class PDBManager:
    def __init__(self, can_client: CANClient, logger: logging.Logger = None):
        self.can = can_client
        self.logger = logger
        self.switch: List[ChannelMetrics] = [ChannelMetrics() for _ in range(8)]
        self.buck1: List[ChannelMetrics] = [ChannelMetrics() for _ in range(2)]
        self.buck2: List[ChannelMetrics] = [ChannelMetrics() for _ in range(2)]
        self.bms: List[float] = [0.0] * 12
        self.source_id = 42

    def register(self, board_id):
        self.can.subscribe(
            board_id, lambda data, b_id=board_id: self.handle_can_message(b_id, data)
        )

    def register_all(self):
        for b_id in BoardID:
            self.register(
                ((0xFF & 0x1F) << 6) | b_id
            )  # source board id, destination all can

    def handle_can_message(self, msg_id: int, data: bytes):
        destination_id, source_id = self.convert_arbitration_id(msg_id)
        command_id = (data[0] >> 4) & 0x0F
        attribute_id = data[0] & 0x0F
        channel_id = (data[1] >> 4) & 0x0F

        # self.logger.info(f"destination_id: {destination_id}")
        # self.logger.info(f"command_id: {command_id}")
        # self.logger.info(f"channel_id: {channel_id}")
        # self.logger.info(f"attribute_id: {attribute_id}")
        if command_id != CommandID.BROADCAST:
            return  # Not broadcast command

        value = struct.unpack_from("<f", data, 2)[0]
        board = self.get_board(source_id)
        attribute = self.get_attribute(attribute_id)

        if board is None:
            return  # Not correct board

        if source_id == BoardID.BMS:  # BMS
            if channel_id < len(self.bms):
                self.bms[channel_id] = value
        else:  # Channel Metrics
            if channel_id < len(board) and attribute:
                setattr(board[channel_id], attribute, value)

    # Helper functions
    def get_board(
        self, board_id: int
    ) -> Optional[Union[List[ChannelMetrics], List[float]]]:
        board_map = {
            BoardID.SWITCH: self.switch,
            BoardID.BUCK1: self.buck1,
            BoardID.BUCK2: self.buck2,
            BoardID.BMS: self.bms,
        }

        board = board_map.get(board_id)

        return board

    @staticmethod
    def get_attribute(attribute_id: int) -> str:
        attribute_map = {
            AttributeID.CURRENT: "current",
            AttributeID.VOLTAGE: "voltage",
            AttributeID.POWER: "power",
            AttributeID.TEMP: "temp",
        }

        attribute_name = attribute_map.get(attribute_id)

        return attribute_name

    @staticmethod
    def convert_arbitration_id(arbitration_id: int) -> tuple[int, int]:
        destination_id = (arbitration_id >> 6) & 0x3F
        source_id = arbitration_id & 0x3F

        return destination_id, source_id

    def get_snapshot(self):
        return {
            "switch": [dataclasses.asdict(m) for m in self.switch],
            "buck1": [dataclasses.asdict(m) for m in self.buck1],
            "buck2": [dataclasses.asdict(m) for m in self.buck2],
            "bms": self.bms,
        }

    async def toggle_channel(self, board_id: int, channel: int, enable: bool):
        can_id = ((board_id & 0x3F) << 6) | (self.source_id & 0x3F)

        byte0 = ((CommandID.TOGGLE & 0x0F) << 4) | 0x0

        toggleState = 1 if enable else 0
        byte1 = ((channel & 0x0F) << 4) | (
            (toggleState & 0x01) << 3
        )  # Channel (4 bits), Toggle State

        data = bytes([byte0, byte1, 0, 0, 0, 0, 0, 0])

        await self.can.send(can_id, data)
