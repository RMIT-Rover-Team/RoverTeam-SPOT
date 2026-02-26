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
            warnings.warn(f"Open Socket Error: {e}")
            warnings.warn(f"Interface Name: {interface_name}")
            raise

    def read_from_socket(self) -> Optional[CanFrame]:
        """Set a filter for can ids on the socket.

        Args:
            slave_ids: a list of slave_ids to filter from.
        """

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
        """Drain all messages from the bus to add to the deque"""
        while True:
            frame = self.read_from_socket()
            if frame is None:
                break

            self.can_buffer.append(frame)

    def read_msg(self) -> Optional[CanFrame]:
        """Adds all messages to the deque then reads the first message from the deque.
        Args:
            slave_ids: a list of slave_ids to filter from.
        """
        self.drain_socket()

        if not self.can_buffer:
            return None
        return self.can_buffer.popleft()

    def read_msg_from(
        self, slave_ids: list[int], mask: int = 0xFC0
    ) -> Optional[CanFrame]:
        """Adds all messages to the deque then reads the first message from the deque that fits the slave_id.
        Args:
            slave_ids: a list of slave_ids to read from.
        """
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

    def set_socket_filter(self, slave_ids: list[int], mask: int = 0xFC0):
        """Set a filter for can ids on the socket.

        Args:
            slave_ids: a list of slave_ids to filter from.
        """

        if not slave_ids:
            print("[WARN] No slave ids passed in.")
            return

        if isinstance(slave_ids, int):  # convert int to int list
            slave_ids = {slave_ids}

        filter_data = b""

        for sid in slave_ids:
            # shift slave ID into correct position
            can_id = (sid & 0x3F) << 6
            filter_data += struct.pack("II", can_id, mask)

        if filter_data:
            self.s.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER, filter_data)
