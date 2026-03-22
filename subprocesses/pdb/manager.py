import datetime
import logging
from dataclasses import asdict
import dataclasses
from typing import List, Optional, Union

from sharedlib.payloadControl import pyRover

from sharedlib.models import (
    PDBID,
    PDBStreamID,
    ChannelMetrics,
    CommandID,
    TelemetryState,
    PDB_ATTRIBUTE_MULTIPLIERS,
)

# imu 4

class PDBManager:
    def __init__(
        self,
        pdb_master: pyRover,
        logger: Optional[logging.Logger] = None,
    ):
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
    def _serialize_item(self, obj):
        if dataclasses.is_dataclass(obj):
            # Convert to dict; asdict() handles nested dataclasses automatically
            # We then loop through to catch Enums
            data = dataclasses.asdict(obj)
            return {k: self._serialize_item(v) for k, v in data.items()}
        elif isinstance(obj, Enum):
            return obj.name
        elif isinstance(obj, (list, tuple)):
            return [self._serialize_item(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: self._serialize_item(v) for k, v in obj.items()}
        return obj
    
    def get_pending_data(self) -> dict:
        pending_data_list = {}
        for board, channels in self.boards.items():
            board_key = board.name.lower()

            for channel_idx, state in enumerate(channels):
                if state.pending_send:
                    if board_key not in pending_data_list:
                        pending_data_list[board_key] = {}
                    
                    # Use the recursive helper here
                    pending_data_list[board_key][channel_idx] = self._serialize_item(state.metric_data)
                    
                    state.pending_send = False 

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
                board.value, 0, channel_id
            )

            # update stored values
            state[channel_id].metric_data = returned_value
            state[channel_id].last_updated = datetime.datetime.now()
            state[channel_id].pending_send = True

        else:
            for attr in PDBStreamID:
                target_channel = state[channel_id].metric_data
                stream_name = self._get_stream(attr)

                if attr == PDBStreamID.POWER: # if attribute is power, calculate power differently                  
                    voltage_name = self._get_stream(PDBStreamID.VOLTAGE)
                    current_name = self._get_stream(PDBStreamID.CURRENT)

                    voltage_value = getattr(target_channel, voltage_name)
                    current_value = getattr(target_channel, current_name)

                    setattr(
                        target_channel,
                        stream_name,
                        voltage_value * current_value
                    )                    
                else:  # else if not power, just calculate normally
                    _, returned_value = self.pdb_master.RequestDataPoint(
                        board.value, attr.value, channel_id
                    )
                    setattr(
                        target_channel,
                        stream_name,
                        self._convert_raw_value(channel_id, returned_value),
                    )
                # update stored values
               
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
    def _get_stream(stream_id: int) -> str:
        stream_map = {
            PDBStreamID.CURRENT.value: "current",
            PDBStreamID.VOLTAGE.value: "voltage",
            PDBStreamID.POWER.value: "power",
            PDBStreamID.TEMP.value: "temp",
            PDBStreamID.TOGGLE.value: "toggle",
        }
        return stream_map.get(stream_id, "")

    @staticmethod
    def _convert_raw_value(channel_id: Union[PDBStreamID, int], raw_value: float):
        return raw_value * PDB_ATTRIBUTE_MULTIPLIERS[PDBStreamID(channel_id)]