from dataclasses import asdict, dataclass
from enum import Enum, IntEnum
import datetime
from typing import Union
import dataclasses


class PDBBoardID(IntEnum):
    SWITCH = 0xA
    BUCK1 = 0x06
    BUCK2 = 0x07
    BMS = 0x08

    @property
    def max_channels(self) -> int:
        """Returns the number of channels/cells allowed for this board."""
        return BOARD_LIMITS[self]

class PDBChannelLength(IntEnum):
    SWITCH = 8
    BUCK1 = 2
    BUCK2 = 2


class PDBCellLength(IntEnum):
    BMS = 12


BOARD_LIMITS = {
    PDBBoardID.SWITCH: PDBChannelLength.SWITCH,
    PDBBoardID.BUCK1: PDBChannelLength.BUCK1,
    PDBBoardID.BUCK2: PDBChannelLength.BUCK2,
    PDBBoardID.BMS: PDBCellLength.BMS,
}


class PDBStreamID(IntEnum):
    CURRENT = 0
    VOLTAGE = 1
    POWER = 2
    TEMP = 3


class CommandID(IntEnum):
    ESTOP = 0x00
    SETPOSITION = 0x02
    TOGGLE = 0x04
    BROADCASTDP = 0x07
    REQUESTDP = 0x08


class AttrMultiplier(Enum):
    VOLTAGEMULTIPLIER = 0.003125
    CURRENTMULTIPLIER = 0.00030517578125
    POWERMULTIPLIER = 0.2 * CURRENTMULTIPLIER
    TEMPMULTIPLIER = 0.125


@dataclass
class ChannelMetrics:
    voltage: float = 0.0
    current: float = 0.0
    power: float = 0.0
    temp: float = 0.0

    def to_dict(self):
        return asdict(self)
    

@dataclass
class TelemetryState:
    metric_data: Union[ChannelMetrics, float]
    last_updated: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.now
    )
    pending_send: bool = False
