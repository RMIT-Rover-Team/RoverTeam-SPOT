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

    def __init__(self, device: str, width: int, height: int, logger: logging.Logger, useSize: bool, fps: int = 15):
        self.device = device
        self.width = width
        self.height = height
        self.logger = logger
        self.useSize = useSize
        self.fps = fps

        self.latest_frame = None
        self.frame_id = 0

        self.clients = 0
        self.client_events = set()

        self.running = False
        self.error = False
        self._lock = threading.Lock()
        self._thread = None
        self._loop = asyncio.get_event_loop()
        self._start_time = time.monotonic()
        self._last_pts = -1

    def start(self):
        if self.running:
            return
        self.running = True
        self.error = False
        
        self._start_time = time.monotonic()
        self._last_pts = -1

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self.logger.info(f"[{self.device}] Broadcaster thread started.")

    def stop(self):
        self.running = False
        self._wake_all_clients()
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
                    # "fflags": "nobuffer",  # Prevent ffmpeg from queuing old frames
                    # "flags": "low_delay",  # Enforce low latency mode
                    "framerate": "1" # use the lowest framerate available
                },
            )
            stream = container.streams.video[0]

            for frame in container.decode(stream):
                if not self.running:
                    break

                yuv_frame = frame.reformat(format="yuv420p")
                timestamp = int((time.monotonic() - self._start_time) * 90000)
                if timestamp <= self._last_pts:
                    timestamp = self._last_pts + 1
                self._last_pts = timestamp
                yuv_frame.pts = timestamp
                yuv_frame.time_base = fractions.Fraction(1, 90000)

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
    
    def get_frame(self):
        with self._lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame


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
        self.device_id = -1

        # Dedicated event to prevent race conditions between multiple viewers
        self._new_frame_event = asyncio.Event()
        with self.broadcaster._lock:
            self.broadcaster.client_events.add(self._new_frame_event)

    def stop(self):
        super().stop()
        with self.broadcaster._lock:
            self.broadcaster.client_events.discard(self._new_frame_event)

    async def recv(self) -> av.VideoFrame:
        while (
            self.broadcaster.latest_frame is None
            or self.last_frame_id == self.broadcaster.frame_id
        ):
            self._new_frame_event.clear()

            # Re-check to ensure we didn't clear the event right as the thread pushed a frame
            if (
                self.broadcaster.latest_frame is not None
                and self.last_frame_id != self.broadcaster.frame_id
            ):
                break

            if not self.broadcaster.running or self.broadcaster.error:
                raise ConnectionError("Camera stream failed or was unplugged")

            await self._new_frame_event.wait()

        with self.broadcaster._lock:
            frame = self.broadcaster.latest_frame
            self.last_frame_id = self.broadcaster.frame_id

        return frame