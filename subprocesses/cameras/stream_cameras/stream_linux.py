import os
import logging
import asyncio
from aiortc import VideoStreamTrack
from aiortc.contrib.media import MediaPlayer

class V4L2CameraTrack(VideoStreamTrack):
    """
    Wraps a MediaPlayer instance for Linux V4L2 camera streaming
    """
    def __init__(self, index: int, label: str, logger: logging.Logger, width=640, height=480):
        super().__init__()
        self.index = index
        self.logger = logger
        self.device = f"/dev/video{index}"

        if not os.path.exists(self.device):
            raise Exception(f"Camera {label} ({index}) not found at {self.device}")

        options = {
            "format": "v4l2",
            "video_size": f"{width}x{height}",
            "framerate": "30",
            "input_format": "mjpeg",  # optional, adjust if needed
        }

        try:
            self.player = MediaPlayer(self.device, format="v4l2", options=options)
        except Exception as e:
            raise Exception(f"Failed to open camera {label} ({index}): {e}")

    async def recv(self):
        """
        Get the next frame from MediaPlayer.video in a way compatible with aiortc.
        """
        if not hasattr(self.player, "video") or self.player.video is None:
            logger.warning("No video track available from MediaPlayer")
            raise asyncio.CancelledError()

        frame = await self.player.video.recv()
        return frame

    def stop(self):
        if hasattr(self, "player") and self.player:
            self.player.stop()
        super().stop()