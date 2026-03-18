import asyncio
import datetime
import logging
import struct
from dataclasses import asdict
from typing import List, Optional, Union

from sharedlib.canbus.client import CANClient
from sharedlib.payloadControl import pyRover

from sharedlib.models import PDBID, PDBStreamID, ChannelMetrics, CommandID, TelemetryState

# imu 4

class PDBManager:
    def __init__(
        self,
        can_client: CANClient,
        pdb_master: pyRover,
        logger: Optional[logging.Logger] = None,
    ):
        self.can = can_client
        self.pdb_master = pdb_master

        self.logger = logger
        self.id = 16

        self._valid_attr_ids = {a.value for a in PDBStreamID}
        self._valid_cmd_ids = {CommandID.REQUESTDP, CommandID.ESTOP}

        self.boards: dict[PDBID, List[TelemetryState]] = {}
        for board in PDBID:
            self.boards[board] = []
            for _ in range(board.max_channels):
                initial_data = 0.0 if board == PDBID.BMS else ChannelMetrics()
                self.boards[board].append(TelemetryState(metric_data=initial_data))
             
                
    # --- PUBLIC APIS ---
    def get_pending_data(self) -> dict:
        pending_data_list = {}
        for board, channels in self.boards.items():
            board_key = board.name.lower()

            for channel_idx, state in enumerate(channels):
                if state.pending_send:
                    for channel_idx, state in enumerate(channels):
                        if state.pending_send:
                            if board_key not in pending_data_list:
                                pending_data_list[board_key] = {}
                            
                            # Convert Dataclass to Dict and Enum to String
                            if isinstance(state.metric_data, ChannelMetrics):
                                pending_data_list[board_key][channel_idx] = asdict(state.metric_data)
                            else:
                                # For BMS which is just a float
                                pending_data_list[board_key][channel_idx] = state.metric_data
                            
                            state.pending_send = False # Reset flag

        return pending_data_list

    async def request_pdb_data(self):
        for board in PDBID:
            await self.request_board_data(board)

    async def request_board_data(self, board_id: Union[int, PDBID]):
        board = PDBID(board_id)  # cast just in case

        for channel_idx in range(board.max_channels):
            await self.request_channel_data(board.value, channel_idx)

    async def request_channel_data(
        self, board_id: Union[int, PDBID], channel_id: int
    ):
        board = PDBID(board_id)
        state = self.boards[board]  # get current board state

        if board == PDBID.BMS:
            _, returned_value = self.pdb_master.RequestDataPoint(
                board.value, channel_id, 0
            )

            # update stored values
            state[channel_id].metric_data = returned_value
            state[channel_id].last_updated = datetime.datetime.now()
            state[channel_id].pending_send = True

        else:
            for  attr in PDBStreamID:
                _, returned_value = self.pdb_master.RequestDataPoint(
                    board.value, attr.value, channel_id
                )
                target_channel = state[channel_id].metric_data
                stream_name = self._get_stream(attr)

                # update stored values
                setattr(target_channel, stream_name, returned_value)
                state[channel_id].last_updated = datetime.datetime.now()
                state[channel_id].pending_send = True

    async def toggle_channel(
        self, board_id: Union[int, PDBID], channel: int, enable: bool
    ):
        self.pdb_master.ToggleState(board_id, channel, enable)

    async def cut_power(self, cell_id: int):
        self.pdb_master.SetMotorPosition(PDBID.BMS, cell_id, 0)

    # unused
    # async def estop(self, board_id: Union[int, PDBID]):
    #     self.pdb_master.estop(0)


    # --- Internal functions ---
    # --- PARSING MSG
    @staticmethod
    def _parse_arbitration_id(arbitration_id: int) -> tuple[int, int]:
        dest_id = (arbitration_id >> 6) & 0x3F
        src_id = arbitration_id & 0x3F

        return dest_id, src_id

    def _parse_can_msg(
        self, msg_id: int, data: bytes
    ) -> tuple[int, int, int, int, int]:
        dest_id, src_id = self._parse_arbitration_id(msg_id)
        cmd_id = (data[0] >> 4) & 0x0F
        stream_id = data[0] & 0x0F
        channel_id = (data[1] >> 4) & 0x0F
        return dest_id, src_id, cmd_id, stream_id, channel_id


    @staticmethod
    def _get_stream(stream_id: int) -> str:
        stream_map = {
            PDBStreamID.CURRENT.value: "current",
            PDBStreamID.VOLTAGE.value: "voltage",
            PDBStreamID.POWER.value: "power",
            PDBStreamID.TEMP.value: "temp",
            PDBStreamID.TOGGLE.value: "toggle",
        }
        return stream_map.get(stream_id, "")


    # --- MISC HELPERS
    @staticmethod
    def _build_arbitration_id(dest_id: int, src_id: int) -> int:
        return ((dest_id & 0x3F) << 6) | (src_id & 0x3F)


    def _validate_msg(
        self,
        dest_id: int,
        src_id: int,
        cmd_id: int,
        stream_id: int,
        channel_id: int,
        data_len: int,
    ) -> bool:
        # Check valid ids
        if dest_id != (self.id & 0x1F) or src_id not in [
            b_id for b_id in PDBID
        ]:
            return False

        if cmd_id not in self._valid_cmd_ids:
            return False

        if data_len < 8:
            return False

        board = PDBID(src_id)

        if src_id == PDBID.BMS:
            return 0 <= stream_id < board.max_channels

        stream_name = self._get_stream(stream_id)
        if not stream_name:
            return False

        if board not in self.boards:
            return False

        return 0 <= channel_id < board.max_channels
