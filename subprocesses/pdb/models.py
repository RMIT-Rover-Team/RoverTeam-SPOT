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


class AttributeID(IntEnum):
    CURRENT = 0
    VOLTAGE = 1
    POWER = 2
    TEMP = 3


class CommandID(IntEnum):
    TOGGLE = 0x04
    BROADCAST = 0x07


class AttributeMultiplier(Enum):
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
