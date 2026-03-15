import os
import asyncio
import logging
import subprocess
import time
import av.container
import av.stream
import numpy as np
from aiortc import VideoStreamTrack
import av
from typing import Optional


class V4L2CameraTrack(VideoStreamTrack):
    WIDTH = 640
    HEIGHT = 480
    FPS = 30

    RETRY_DELAY = 2
    MAX_RETRIES = 10

    kind = "video"

    def __init__(self, index: int, label: str, logger: logging.Logger, width: int, height: int):
        super().__init__()
        self.index = index
        self.label = label
        self.logger = logger
        self.device = f"/dev/video{index}"
        self.container: Optional[av.container.InputContainer] = None
        self.stream: Optional[av.stream.Stream] = None

        self.WIDTH = width
        self.HEIGHT = height

        if not os.path.exists(self.device):
            raise RuntimeError(f"{self.device} not found")

    # --------------------------------------------------

    def _open_device(self):
        self._cleanup()
        
        self.container = av.open(
            self.device,
            format="v4l2",
            options={
                "video_size": f"{self.WIDTH}x{self.HEIGHT}",
                "pixel_format": "mjpeg",  # Or 'yuyv422'
            },
        )
        self.stream = self.container.streams.video[0]
        self.logger.info(f"[{self.label}] Opened with PyAV")

    # --------------------------------------------------
    
    async def recv(self) -> av.VideoFrame:
        if self.container is None or self.stream is None:
            self._open_device()

        loop = asyncio.get_event_loop()
        try:
            
            # Get next frame from the generator
            # We use next() on the decode generator
            if not self.container:
                raise TypeError("Expected container")
            frame = await loop.run_in_executor(None, lambda: next(self.container.decode(self.stream)))

            # Ensure the frame is a video frame
            if not isinstance(frame, av.VideoFrame):
                raise TypeError("Expected av.VideoFrame")

            # Calculate timing
            pts, time_base = await self.next_timestamp()
            frame.pts = pts
            frame.time_base = time_base

            return frame
        except (StopIteration, Exception) as e:
            self.logger.error(f"[{self.label}] Camera error: {e}")
            self._cleanup()
            raise ConnectionError("Camera stream failed")

    # --------------------------------------------------

    def _cleanup(self):
        if self.container:
            try:
                self.container.close()
            except Exception:
                pass
        self.container = None
        self.stream = None

    # --------------------------------------------------

    def stop(self):
        self._cleanup()
        super().stop()