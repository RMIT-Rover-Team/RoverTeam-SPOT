import asyncio
import zmq
import zmq.asyncio
from typing import Callable, Dict, List, Optional


class CANClient:
    """
    Async client for talking to the CAN daemon subprocess.
    Allows sending messages and subscribing to specific CAN IDs.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        pub_addr: str = "tcp://127.0.0.1:5556",
        rep_addr: str = "tcp://127.0.0.1:5557",
    ):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.ctx = zmq.asyncio.Context()
        self.pub_addr = pub_addr
        self.rep_addr = rep_addr

        # SUB socket for incoming CAN messages
        self.sub_socket = self.ctx.socket(zmq.SUB)
        self.sub_socket.connect(pub_addr)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")  # subscribe to nothing initially

        # REQ socket for sending CAN messages
        self.req_socket = self.ctx.socket(zmq.REQ)
        self.req_socket.connect(rep_addr)

        # msg_id -> list of callbacks
        self._subscriptions: Dict[int, List[Callable]] = {}

        self._recv_task: Optional[asyncio.Task] = None
        self._running = False

    # -------------------------
    # Lifecycle
    # -------------------------

    async def start(self):
        """Start background receive loop (must be called inside event loop)."""
        if self._running:
            return
        self._running = True
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def close(self):
        """Clean shutdown."""
        self._running = False

        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass

        self.sub_socket.close(0)
        self.req_socket.close(0)
        self.ctx.term()

    # -------------------------
    # Internal Receive Loop
    # -------------------------

    async def _recv_loop(self):
        """Listen for incoming CAN messages and dispatch to subscribers."""
        while self._running:
            try:
                topic_bytes, data = await self.sub_socket.recv_multipart()
                msg_id = int(topic_bytes.decode())

                callbacks = self._subscriptions.get(msg_id, [])
                for cb in callbacks:
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.create_task(cb(data))
                    else:
                        cb(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"CANClient receive error: {e}")
                await asyncio.sleep(0.01)

    # -------------------------
    # Public API
    # -------------------------

    async def send(self, msg_id: int, data: bytes):
        """Send a CAN message through the daemon."""
        try:
            await self.req_socket.send_multipart(
                [str(msg_id).encode(), data]
            )
            await self.req_socket.recv()  # discard reply
        except Exception as e:
            print(f"CANClient send error: {e}")

    def subscribe(self, msg_id: int, callback: Callable[[bytes], None]):
        """Register a callback for a specific CAN ID."""
        if msg_id not in self._subscriptions:
            self._subscriptions[msg_id] = []
            self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, str(msg_id))
        self._subscriptions[msg_id].append(callback)