import asyncio
import struct
import websockets


class CanTelemetryServer:
    BIN_FMT = struct.Struct("<IB8s")

    def __init__(self):
        self.clients = set()

    async def handle_connection(self, websocket):
        self.clients.add(websocket)
        try:
            async for _ in websocket:
                pass
        finally:
            self.clients.remove(websocket)
        pass

    async def _broadcast(self, frame):
        if not self.clients:
            return

        padded_data = frame.data.ljust(8, b"\x00")
        pkt = self.BIN_FMT.pack(frame.can_id, frame.can_dlc, padded_data)

        await asyncio.gather(
            *[c.send(pkt) for c in self.clients], return_exceptions=True
        )
