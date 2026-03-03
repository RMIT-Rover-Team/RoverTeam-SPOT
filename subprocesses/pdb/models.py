from dataclasses import asdict, dataclass
from enum import IntEnum


class MasterID(IntEnum):
    EQUINOX_1 = 0x1
    EQUINOX_2 = 0x2


class BoardID(IntEnum):
    SWITCH_ID = 0xA
    BUCK1_ID = 0x06
    BUCK2_ID = 0x07
    BMS_ID = 0x08


class AttributeID(IntEnum):
    CURRENT = 0
    VOLTAGE = 1
    POWER = 2
    TEMP = 3


class CommandID(IntEnum):
    TOGGLE = 0x04
    BROADCAST = 0x07


@dataclass
class ChannelMetrics:
    voltage: float = 0.0
    current: float = 0.0
    power: float = 0.0
    temp: float = 0.0

    def to_dict(self):
        return asdict(self)
