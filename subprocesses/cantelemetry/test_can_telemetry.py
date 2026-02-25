import subprocess
import time
from .canbus.can_wrapper import WrappedCanbus


# COMMAND:
# PYTHONPATH="" poetry run pytest


def test_read_msg():
    bus = WrappedCanbus("vcan0")

    master_id, slave_id = 0x01, 0x03

    header = 0
    header = f"{((slave_id & 0x3F) << 6) | (master_id & 0x3F):03x}"

    data_str = "12"
    subprocess.run(["cansend", "vcan0", f"{header}#{data_str}"])
    time.sleep(0.01)
    frame = bus.read_msg()

    assert frame is not None
    assert frame.can_id == 0xC1
    assert frame.data == b"\x12"

    assert frame.can_id != 0x31
    assert frame.data != b"\x67"


def test_read_msg_from():
    bus = WrappedCanbus("vcan0")

    master_id, slave_id_1, slave_id_2 = 0x01, 0x03, 0x4
    header_1 = 0
    header_1 = f"{((slave_id_1 & 0x3F) << 6 | (master_id & 0x3F)):03x}"

    header_2 = 0
    header_2 = f"{((slave_id_2 & 0x3F) << 6) | (master_id & 0x3F):03x}"

    data_str_1 = "12"
    data_str_2 = "34"

    subprocess.run(["cansend", "vcan0", f"{header_1}#{data_str_1}"])
    subprocess.run(["cansend", "vcan0", f"{header_2}#{data_str_2}"])

    time.sleep(0.01)
    frame = bus.read_msg_from({0x101}, 0xFFF)

    assert frame is not None
    assert frame.can_id == 0x101
    assert frame.data == b"\x34"

    assert frame.can_id != 0xC1
    assert frame.data != b"\x12"

    frame = bus.read_msg_from({0xC1}, 0xFFF)

    assert frame is not None
    assert frame.can_id == 0xC1
    assert frame.data == b"\x12"

    assert frame.can_id != 0x101
    assert frame.data != b"\x34"
