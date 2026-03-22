from dataclasses import asdict, dataclass
from enum import Enum, IntEnum
import datetime
from typing import Union
import dataclasses


class BoardID(IntEnum):
    SCIENCE = 0xB
    SWITCH = 0xA
    BUCK1 = 0x06
    BUCK2 = 0x07
    BMS = 0x08
    

class ScienceID(IntEnum):
    DRILL = 0
    MICROSCOPE_SWIVEL = 1
    MICROSCOPE = 2
    AUGER = 3
    HEATER = 4
    PELTIER = 5
    HEATER_SENSOR = 4


class PDBID(IntEnum):
    SWITCH = BoardID.SWITCH
    BUCK1 = BoardID.BUCK1
    BUCK2 = BoardID.BUCK2
    BMS = BoardID.BMS

    @property
    def max_channels(self) -> int:
        """Returns the number of channels/cells allowed for this board."""
        return PDB_BOARD_LIMITS[self]


class PDBChannelLength(IntEnum):
    SWITCH = 8
    BUCK1 = 2
    BUCK2 = 2


class PDBCellLength(IntEnum):
    BMS = 12


PDB_BOARD_LIMITS = {
    PDBID.SWITCH: PDBChannelLength.SWITCH,
    PDBID.BUCK1: PDBChannelLength.BUCK1,
    PDBID.BUCK2: PDBChannelLength.BUCK2,
    PDBID.BMS: PDBCellLength.BMS,
}


class PDBStreamID(IntEnum):
    CURRENT = 0
    VOLTAGE = 1
    POWER = 2
    TEMP = 3
    TOGGLE = 4


class CommandID(IntEnum):
    ESTOP = 0x00
    CALIBRATE = 0x1
    SETPOSITION = 0x02
    SETSPEED = 0x3
    TOGGLE = 0x04
    GETPOSITION = 0x05
    GETSPEED = 0x6
    BROADCASTDP = 0x07
    REQUESTDP = 0x08


PDB_ATTRIBUTE_MULTIPLIERS = {
    PDBStreamID.VOLTAGE: 0.003125,
    PDBStreamID.CURRENT: 0.00030517578125,
    PDBStreamID.POWER: 0.2 * 0.00030517578125,
    PDBStreamID.TEMP: 0.125,
    PDBStreamID.TOGGLE: 1,
}

class AttrMultiplier(Enum):
    VOLTAGEMULTIPLIER = 0.003125
    CURRENTMULTIPLIER = 0.00030517578125
    POWERMULTIPLIER = 0.00006103515
    TEMPMULTIPLIER = 0.125


@dataclass
class ChannelMetrics:
    voltage: float = 0.0
    current: float = 0.0
    power: float = 0.0
    temp: float = 0.0
    toggle: bool = False

    def to_dict(self):
        return asdict(self)
    

@dataclass
class TelemetryState:
    metric_data: Union[ChannelMetrics, float]
    last_updated: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.now
    )
    pending_send: bool = False
