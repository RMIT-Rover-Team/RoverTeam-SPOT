import asyncio
import zmq
import zmq.asyncio
from typing import Callable, Dict, List, Optional


class CANClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        pub_addr: str = "tcp://127.0.0.1:5556",
        rep_addr: str = "tcp://127.0.0.1:5557",
        push_addr: str = "tcp://127.0.0.1:5560",  # NEW push port
    ):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.ctx = zmq.asyncio.Context()

        # Subscribe for incoming CAN messages
        self.sub_socket = self.ctx.socket(zmq.SUB)
        self.sub_socket.connect(pub_addr)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        # REQ for blocking sends
        self.req_socket = self.ctx.socket(zmq.REQ)
        self.req_socket.connect(rep_addr)

        # PUSH for fire-and-forget sends
        self.push_socket = self.ctx.socket(zmq.PUSH)
        self.push_socket.connect(push_addr)

        # Subscriptions
        self._subscriptions: Dict[int, List[Callable]] = {}
        self._recv_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def close(self):
        self._running = False
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        self.sub_socket.close(0)
        self.req_socket.close(0)
        self.push_socket.close(0)
        self.ctx.term()

    async def _recv_loop(self):
        while self._running:
            try:
                topic_bytes, data = await self.sub_socket.recv_multipart()
                msg_id = int(topic_bytes.decode())
                for cb in self._subscriptions.get(msg_id, []):
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.create_task(cb(data))
                    else:
                        cb(data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"CANClient receive error: {e}")
                await asyncio.sleep(0.001)

    # Blocking send (REQ)
    async def send(self, msg_id: int, data: bytes):
        try:
            await self.req_socket.send_multipart([str(msg_id).encode(), data])
            await self.req_socket.recv()
        except Exception as e:
            print(f"CANClient send error: {e}")

    # Fire-and-forget send (PUSH)
    async def send_nowait(self, msg_id: int, data: bytes):
        try:
            await self.push_socket.send_multipart([str(msg_id).encode(), data])
        except Exception as e:
            print(f"CANClient fire-and-forget send error: {e}")

    def subscribe(self, msg_id: int, callback: Callable[[bytes], None]):
        if msg_id not in self._subscriptions:
            self._subscriptions[msg_id] = []
            self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, str(msg_id))
        self._subscriptions[msg_id].append(callback)