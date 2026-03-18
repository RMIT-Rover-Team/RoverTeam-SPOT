import os
import asyncio
import threading
import logging
import time
import numpy as np
import av
from aiortc import VideoStreamTrack


class CameraBroadcaster:
    """
    Reads from the camera in a dedicated background thread to prevent buffer bloat
    and shares the latest frame with multiple WebRTC clients.
    """

    def __init__(self, device: str, width: int, height: int, logger: logging.Logger):
        self.device = device
        self.width = width
        self.height = height
        self.logger = logger

        self.latest_frame_array = None
        self.frame_id = 0

        self.running = False
        self._lock = threading.Lock()
        self._thread = None
        self._loop = asyncio.get_event_loop()
        self._new_frame_event = asyncio.Event()

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self.logger.info(f"[{self.device}] Broadcaster thread started.")

    def stop(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.logger.info(f"[{self.device}] Broadcaster thread stopped.")

    def _capture_loop(self):
        """Runs in a standard Python Thread."""
        container = None
        try:
            container = av.open(
                self.device,
                format="v4l2",
                options={
                    "video_size": f"{self.width}x{self.height}",
                    "pixel_format": "mjpeg",  # or yuyv422
                },
            )
            stream = container.streams.video[0]

            for frame in container.decode(stream):
                if not self.running:
                    break

                # Convert to numpy array immediately.
                # We CANNOT share av.VideoFrame directly because aiortc modifies it.
                frame_array = frame.to_ndarray(format="bgr24")

                with self._lock:
                    self.latest_frame_array = frame_array
                    self.frame_id += 1

                # Notify the asyncio loop that a new frame is ready
                self._loop.call_soon_threadsafe(self._new_frame_event.set)

        except Exception as e:
            self.logger.error(f"[{self.device}] Capture loop error: {e}")
        finally:
            if container:
                container.close()


class SharedCameraTrack(VideoStreamTrack):
    """
    A lightweight proxy track created for EACH connected WebRTC client.
    It reads from the global CameraBroadcaster.
    """

    kind = "video"

    def __init__(self, broadcaster: CameraBroadcaster):
        super().__init__()
        self.broadcaster = broadcaster
        self.last_frame_id = -1

    async def recv(self) -> av.VideoFrame:
        # Wait until the broadcaster captures a NEW frame
        while self.last_frame_id == self.broadcaster.frame_id:
            await self.broadcaster._new_frame_event.wait()
            self.broadcaster._new_frame_event.clear()

        # Safely grab the latest frame array
        with self.broadcaster._lock:
            frame_array = self.broadcaster.latest_frame_array
            self.last_frame_id = self.broadcaster.frame_id

        if frame_array is None:
            raise ConnectionError("No frame available from broadcaster")

        # Convert back to an av.VideoFrame for aiortc
        new_frame = av.VideoFrame.from_ndarray(frame_array, format="bgr24")

        # aiortc handles the timing math based on when next_timestamp() is called
        pts, time_base = await self.next_timestamp()
        new_frame.pts = pts
        new_frame.time_base = time_base

        return new_frame
