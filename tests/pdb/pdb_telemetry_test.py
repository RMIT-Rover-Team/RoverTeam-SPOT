import struct
from unittest.mock import MagicMock

import pytest

from subprocesses.pdb.telemetry.manager import PDBManager


@pytest.fixture
def manager():
    # Mock the can_client so we don't need a real bus for logic tests
    mock_can = MagicMock()
    return PDBManager(mock_can)


def test_id_conversion(manager):
    """Tests if the 12-bit ID is split into 6-bit Dest and 6-bit Source."""
    msg_id = (0xFF << 6) | 0x06  # Dest: 0xFF (Everything),  Source: 0x6 (Buck1)
    dest, src = manager.convert_arbitration_id(msg_id)
    assert dest == 0xFF & 0x3F
    assert src == 0x06 & 0x3F


def test_handle_switch_voltage(manager):
    """Tests updating a ChannelMetrics object (Switch Board)."""
    msg_id = (0xFF << 6) | 0x0A  # setup ID for SWITCH_ID (0x0A)
    byte0 = 0x71  # Command 7, Attribute 1 (Voltage) -> 0x71
    byte1 = 0x50  # Channel 5, empty 4 bits
    val = 12.5  # float val

    data = bytearray(8)
    data[0] = byte0
    data[1] = byte1
    struct.pack_into(">f", data, 2, val)  # pack with big endian

    # 4. Process
    manager.handle_can_message(msg_id, bytes(data))

    # 5. Assert
    assert manager.switch[5].voltage == pytest.approx(12.5)
    assert manager.switch[5].current == 0.0  # Ensure other fields aren't touched


def test_handle_bms_list(manager):
    """Tests updating the BMS list (which is List[float], not List[ChannelMetrics])."""
    msg_id = (0xFF << 6) | 0x08  # BMS_ID is 0x08
    byte0 = 0x7B  # Commmand 7, Attribute 0
    byte1 = 0xB0  # Channel 11
    val = 3.99  # float val

    data = bytearray(8)
    data[0] = byte0
    data[1] = byte1
    struct.pack_into(">f", data, 2, val)  # pack with big endian

    manager.handle_can_message(msg_id, bytes(data))

    assert manager.bms[11] == pytest.approx(3.99)


def test_malformed_data_safety(manager):
    """Ensure the manager doesn't crash if it gets a short message."""
    msg_id = 0x0A << 6
    short_data = b"\x01\x00"  # Too short to contain a float at index 3

    # This should return safely without raising struct.error
    manager.handle_can_message(msg_id, short_data)
