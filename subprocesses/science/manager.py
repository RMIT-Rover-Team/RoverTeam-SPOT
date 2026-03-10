import asyncio
import datetime
import logging
import struct
from dataclasses import asdict
from typing import List, Optional, Union

from sharedlib.models import BoardID, CommandID
from sharedlib.canbus.client import CANClient
from sharedlib.payloadControl import pyRover

# from models import
# imu 4


class ScienceManager:
    def __init__(
        self,
        can_client: CANClient,
        payload_master: pyRover,
        logger: Optional[logging.Logger] = None,
    ):
        self.can = can_client
        self.payload_master = payload_master

        self.logger = logger
        self.id = 12

        self.target_pos = -1
        self.current_pos = -1

        self.temp_state = {
            "peltier": False,
            "heatpad": False,
        }

        # validation
        self._valid_cmd_ids = {
            CommandID.ESTOP,
            CommandID.TOGGLE, 
            CommandID.SETSPEED,
            CommandID.GETSPEED,
        }


    # --- PUBLIC APIS ---
    def handle_can_message(self, msg_id: int, data: bytes):
        dest_id, src_id, cmd_id, stream_id, channel_id = self._parse_can_msg(
            msg_id, data
        )

        is_valid_msg = self._validate_msg(
            dest_id, src_id, cmd_id, stream_id, channel_id, len(data)
        )

        if not is_valid_msg:
            return

        # board_enum = BoardID(src_id)
        # state = self.boards[board_enum]

        # value = struct.unpack_from("<f", data, 2)[0]

        # stream_name = self._get_stream(stream_id)

        # if src_id == BoardID.BMS:  # BMS
        #     state[stream_id].metric_data = value
        # else:  # Channel Metrics
        #     stream_name = self._get_stream(stream_id)
        #     state[stream_id].last_updated = datetime.datetime.now()
        #     state[stream_id].pending_send = True
        #     if stream_name:
        #         target_channel = state[channel_id].metric_data

        #         setattr(target_channel, stream_name, value)
        #         state[channel_id].last_updated = datetime.datetime.now()
        #         state[channel_id].pending_send = True

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
                                pending_data_list[board_key][channel_idx] = asdict(
                                    state.metric_data
                                )
                            else:
                                # For BMS which is just a float
                                pending_data_list[board_key][channel_idx] = (
                                    state.metric_data
                                )

                            state.pending_send = False  # Reset flag

        return pending_data_list

    async def request_pdb_data(self):
        for board in BoardID:
            await self.request_board_data(board)

    async def request_board_data(self, board_id: Union[int, BoardID]):
        board = BoardID(board_id)  # cast just in case

        for channel_idx in range(board.max_channels):
            await self.request_channel_data(board, channel_idx)
            await asyncio.sleep(0.005)

    async def request_channel_data(
        self, board_id: Union[int, BoardID], channel_id: int
    ):
        board = BoardID(board_id)
        if board == BoardID.BMS:
            await self._send_data_request(board.value, stream_id=channel_id)
        else:
            for attr in AttrID:
                await self._send_data_request(
                    board.value, stream_id=attr.value, channel_id=channel_id
                )

    async def toggle_channel(
        self, board_id: Union[int, BoardID], channel: int, enable: bool
    ):
        # OLD CANBUS LOGIC. HERE JUST IN CASE THE FIRMWARE SHITS THE BED
        # can_id = self._build_arbitration_id(board_id, self.id)

        # byte0 = (CommandID.TOGGLE & 0x0F) << 4

        # toggle_state = 1 if enable else 0
        # byte1 = ((channel & 0x0F) << 4) | ((toggle_state & 0x01) << 3)

        # data = bytearray(8)
        # data[0] = byte0
        # data[1] = byte1

        # await self.can.send(can_id, bytes(data))
        toggle_state_result = await self.payload_master.ToggleState(
            board_id, channel, enable
        )

        # toggle_state_result["error_flag"]

    async def cut_power(self, cell_id: int):
        cut_power_result = await self.payload_master.SetMotorPosition(cell_id, 0, 0)

    async def estop(self, board_id: Union[int, BoardID]):
        # can_id = self._build_arbitration_id(board_id, self.id)

        # data = bytearray(8)
        # await self.can.send(can_id, bytes(data))

        estop_result = await self.payload_master.estop(0)

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
            AttrID.CURRENT.value: "current",
            AttrID.VOLTAGE.value: "voltage",
            AttrID.POWER.value: "power",
            AttrID.TEMP.value: "temp",
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
        if dest_id != (self.id & 0x1F) or src_id != BoardID.SCIENCE:
            return False

        if cmd_id not in self._valid_cmd_ids:
            return False

        if data_len < 8:
            return False

        # board = BoardID(src_id)

        # if src_id == BoardID.BMS:
        #     return 0 <= stream_id < board.max_channels

        # stream_name = self._get_stream(stream_id)
        # if not stream_name:
        #     return False

        # if board not in self.boards:
        #     return False

        # return 0 <= channel_id < board.max_channels

    # --- SEND COMMANDS
    async def _send_data_request(
        self, board_id: int, stream_id: int, channel_id: int = 0
    ):
        can_id = self._build_arbitration_id(board_id, self.id)

        byte0 = ((CommandID.REQUESTDP & 0x0F) << 4) | (stream_id & 0x0F)
        byte1 = (channel_id & 0x0F) << 4

        data = bytearray(8)
        data[0] = byte0
        data[1] = byte1

        await self.can.send(can_id, bytes(data))
