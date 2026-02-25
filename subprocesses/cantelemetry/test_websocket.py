import asyncio
import struct
import pytest
import websockets
from .telemetry_ws.server import CanTelemetryServer


class MockCanFrame:
    def __init__(self, can_id, can_dlc, data):
        self.can_id = can_id
        self.can_dlc = can_dlc
        self.data = data


@pytest.mark.asyncio
async def test_websocket_broadcast():
    server = CanTelemetryServer()

    async with websockets.serve(server.handle_connection, "127.0.0.1", 8765):
        async with websockets.connect("ws://127.0.0.1:8765") as client:
            await asyncio.sleep(0.01)

            assert len(server.clients) == 1

            frame = MockCanFrame(can_id=0x101, can_dlc=2, data=b"\x34\x12")

            await server._broadcast(frame)

            received_bytes = await asyncio.wait_for(client.recv(), timeout=1.0)

            expected_bytes = struct.pack(
                "<IB8s", 0x101, 2, b"\x34\x12\x00\x00\x00\x00\x00\x00"
            )

            assert received_bytes == expected_bytes
