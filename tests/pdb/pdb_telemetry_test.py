import struct
from unittest.mock import MagicMock
import pytest

from subprocesses.pdb.telemetry.manager import PDBManager
from subprocesses.pdb.models import BoardID

@pytest.fixture
def manager():
    # Mock the can_client so we don't need a real bus for logic tests
    mock_can = MagicMock()
    # mock_master = pyRover("can0", 16)
    mock_master = MagicMock()
    return PDBManager(mock_can, mock_master)


def test_id_conversion(manager):
    """Tests if the 12-bit ID is split into 6-bit Dest and 6-bit Source."""
    msg_id = manager._build_arbitration_id(
        manager.id, 0x06
    )  # Dest: 41 (manager),  Source: 0x6 (Buck1)
    dest, src = manager._parse_arbitration_id(msg_id)

    assert dest == 16 & 0x3F
    assert src == 0x06 & 0x3F


def test_handle_switch_voltage(manager):
    """Tests updating a ChannelMetrics object (Switch Board)."""
    msg_id = manager._build_arbitration_id(
        manager.id & 0x1f, 0x0A
    )  # setup ID for SWITCH_ID (0x0A). Mask with 0x1f to simulate last bit being cut off due to arbitration id limitations
    byte0 = 0x81  # Command 8, Stream 1 (Voltage) -> 0x81
    byte1 = 0x50  # Channel 5, empty 4 bits
    val = 12.5  # float val

    data = bytearray(8)
    data[0] = byte0
    data[1] = byte1
    struct.pack_into("<f", data, 2, val)  # pack with lil' endian

    # 4. Process
    manager.handle_can_message(msg_id, bytes(data))

    # 5. Assert
    assert manager.boards[BoardID.SWITCH].metric_data[5].voltage == pytest.approx(12.5)
    assert manager.boards[BoardID.SWITCH].metric_data[5].current == 0.0  # Ensure other fields aren't touched


def test_handle_bms_list(manager):
    """Tests updating the BMS list (which is List[float], not List[ChannelMetrics])."""
    msg_id = manager._build_arbitration_id(manager.id & 0x1F, 0x08)  # setup ID for BMS_ID (0x08). Mask destination with 0x1f to simulate last bit being cut off.
    byte0 = 0x8B  # Commmand 8, Stream 11
    val = 3.99  # float val

    data = bytearray(8)
    data[0] = byte0
    struct.pack_into("<f", data, 2, val)  # pack with lil' endian

    manager.handle_can_message(msg_id, bytes(data))

    assert manager.boards[BoardID.BMS].metric_data[11] == pytest.approx(3.99)


def test_malformed_data_safety(manager):
    """Ensure the manager doesn't crash if it gets a short message."""
    msg_id = 0x0A << 6
    short_data = b"\x01\x00"  # Too short to contain a float at index 3

    # This should return safely without raising struct.error
    manager.handle_can_message(msg_id, short_data)
