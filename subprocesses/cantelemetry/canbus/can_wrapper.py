import errno
import select
import socket
import struct
import warnings
from dataclasses import dataclass, field
from collections import deque
from typing import Iterable, List, Optional


@dataclass
class CanFrame:
    can_id: int
    can_dlc: int
    data: bytes


class WrappedCanbus:
    CAN_FRAME_FMT = struct.Struct("=IB3x8s")

    def __init__(self, interface_name: str):
        try:
            self.s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            self.s.bind((interface_name,))
            self.s.setblocking(False)

            self.can_buffer: deque[CanFrame] = deque(maxlen=500)
            self.telemetry_ids: set[int] = {0x01, 0x02, 0x03}
        except OSError as e:
            warnings.warn(f"Open Socket Error:, {e}")
            raise

    def set_socket_filter(self, slave_ids):
        filter_data = b""

        if not slave_ids:
            return

        if isinstance(slave_ids, int):
            slave_ids = {slave_ids}

        mask = 0xFC0

        filter_data = b""

        for sid in slave_ids:
            # Shift the slave ID into the correct position
            can_id = (sid & 0x3F) << 6
            filter_data += struct.pack("II", can_id, mask)

        if filter_data:
            self.s.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER, filter_data)

    def read_from_socket(self) -> Optional[CanFrame]:
        try:
            raw_bytes = self.s.recv(16)

            if len(raw_bytes) < 16:
                warnings.warn(
                    f"Incomplete packet size, size received: {len(raw_bytes)}"
                )
                return None

            can_id, can_dlc, data = self.CAN_FRAME_FMT.unpack(raw_bytes)

            can_id &= 0xFFF

            return CanFrame(can_id=can_id, can_dlc=can_dlc, data=data[:can_dlc])
        except OSError as e:
            if e.errno != errno.EAGAIN:
                print(f"Socket Read Error: {e}")
            return None

    def drain_socket(self) -> None:

        while True:
            frame = self.read_from_socket()
            if frame is None:
                break

            self.can_buffer.append(frame)

    def read_msg(self) -> CanFrame:
        self.drain_socket()

        if not self.can_buffer:
            return None
        return self.can_buffer.popleft()

    def read_msg_from(self, slave_ids, mask=0xFC0):
        self.drain_socket()

        if isinstance(slave_ids, int):
            slave_ids = {slave_ids}

        target_ids = {(sid & 0x3F) << 6 for sid in slave_ids}

        for i, frame in enumerate(self.can_buffer):
            if (frame.can_id & mask) in target_ids:
                match = self.can_buffer[i]
                del self.can_buffer[i]
                return match

        return None
