import os
import asyncio
import threading
import logging
import sys
import time
import fractions
import av
from aiortc import VideoStreamTrack


# Global dictionary to hold our running broadcasters
ACTIVE_BROADCASTERS = {}


class CameraBroadcaster:
    """
    Reads from the camera in a dedicated background thread.
    Grabs frames as fast as possible to keep the hardware buffer completely empty.
    """

    def __init__(self, device: str, width: int, height: int, logger: logging.Logger):
        self.device = device
        self.width = width
        self.height = height
        self.logger = logger

        self.latest_frame = None
        self.frame_id = 0

        self.clients = 0
        self.client_events = set()

        self.running = False
        self.error = False
        self._lock = threading.Lock()
        self._thread = None
        self._loop = asyncio.get_event_loop()

    def start(self):
        if self.running:
            return
        self.running = True
        self.error = False
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self.logger.info(f"[{self.device}] Broadcaster thread started.")

    def stop(self):
        self.running = False
        self._wake_all_clients()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.logger.info(f"[{self.device}] Broadcaster thread stopped.")

    def _wake_all_clients(self):
        with self._lock:
            events = list(self.client_events)
        for e in events:
            self._loop.call_soon_threadsafe(e.set)

    def _capture_loop(self):
        container = None
        try:
            if not os.path.exists(self.device):
                raise RuntimeError(f"{self.device} not found")

            container = av.open(
                self.device,
                format="v4l2",
                options={
                    "video_size": f"{self.width}x{self.height}",
                    "pixel_format": "mjpeg",
                    "fflags": "nobuffer",  # Prevent ffmpeg from queuing old frames
                    "flags": "low_delay",  # Enforce low latency mode
                },
            )
            stream = container.streams.video[0]

            for frame in container.decode(stream):
                if not self.running:
                    break

                with self._lock:
                    self.latest_frame = frame
                    self.frame_id += 1

                # Instantly notify all viewers that a new frame is ready
                self._wake_all_clients()

        except Exception as e:
            self.logger.error(f"[{self.device}] Camera unplugged or capture error: {e}")
            self.error = True
        finally:
            if container:
                try:
                    container.close()
                except Exception:
                    pass
            self.running = False
            self.error = True
            self._wake_all_clients()


class SharedCameraTrack(VideoStreamTrack):
    """
    A lightweight proxy track created for EACH connected WebRTC client.
    """

    kind = "video"

    def __init__(self, broadcaster: CameraBroadcaster):
        super().__init__()
        self.broadcaster = broadcaster
        self.last_frame_id = -1
        self._start_time = None

        # Dedicated event to prevent race conditions between multiple viewers
        self._new_frame_event = asyncio.Event()
        with self.broadcaster._lock:
            self.broadcaster.client_events.add(self._new_frame_event)

    def stop(self):
        super().stop()
        with self.broadcaster._lock:
            self.broadcaster.client_events.discard(self._new_frame_event)

    async def recv(self) -> av.VideoFrame:
        # If we already processed the latest frame, wait for the next one.
        # If we are behind (dropped frames), skip the wait to catch up instantly.
        if self.last_frame_id == self.broadcaster.frame_id:
            self._new_frame_event.clear()
            await self._new_frame_event.wait()

        with self.broadcaster._lock:
            if not self.broadcaster.running or self.broadcaster.error:
                raise ConnectionError("Camera stream failed or was unplugged")
            frame = self.broadcaster.latest_frame
            self.last_frame_id = self.broadcaster.frame_id

        if frame is None:
            raise ConnectionError("No frame available from broadcaster")

        # Convert to WebRTC's native format
        new_frame = frame.reformat(format="yuv420p")

        # THE FIX: Generate True Real-Time Timestamps.
        # This completely overrides aiortc's pacing and forces the WebRTC
        # browser player to display the frame exactly as it was captured,
        # eliminating all snapping and lagging.
        if self._start_time is None:
            self._start_time = time.monotonic()

        # WebRTC uses a 90kHz clock for video timestamps
        timestamp = int((time.monotonic() - self._start_time) * 90000)

        new_frame.pts = timestamp
        new_frame.time_base = fractions.Fraction(1, 90000)

        return new_frame