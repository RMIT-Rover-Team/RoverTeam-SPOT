from dataclasses import asdict, dataclass
from enum import Enum, IntEnum


class MasterID(IntEnum):
    EQUINOX_1 = 0x1
    EQUINOX_2 = 0x2


class BoardID(IntEnum):
    SWITCH = 0xA
    BUCK1 = 0x06
    BUCK2 = 0x07
    BMS = 0x08

    @property
    def max_channels(self) -> int:
        """Returns the number of channels/cells allowed for this board."""
        return BOARD_LIMITS[self]

class ChannelLength(IntEnum):
    SWITCH = 8
    BUCK1 = 2
    BUCK2 = 2


class CellLength(IntEnum):
    BMS = 12


BOARD_LIMITS = {
    BoardID.SWITCH: ChannelLength.SWITCH,
    BoardID.BUCK1: ChannelLength.BUCK1,
    BoardID.BUCK2: ChannelLength.BUCK2,
    BoardID.BMS: CellLength.BMS,
}


class AttrID(IntEnum):
    CURRENT = 0
    VOLTAGE = 1
    POWER = 2
    TEMP = 3


class CommandID(IntEnum):
    ESTOP = 0x00
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
