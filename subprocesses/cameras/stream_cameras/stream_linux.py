import os
import logging
import asyncio
import subprocess
from aiortc import VideoStreamTrack
from aiortc.contrib.media import MediaPlayer
from av import VideoFrame

class V4L2CameraTrack(VideoStreamTrack):
    """
    Robust Linux V4L2 camera track for mission-critical streaming.
    Ensures /dev/videoX is free, retries until success, and handles dead frames.
    """
    RETRY_INTERVAL = 2  # seconds
    FIRST_FRAME_TIMEOUT = 5  # seconds

    def __init__(self, index: int, label: str, logger: logging.Logger, width=640, height=480):
        super().__init__()
        self.index = index
        self.label = label
        self.logger = logger
        self.device = f"/dev/video{index}"
        self.width = width
        self.height = height
        self.options = {
            "format": "v4l2",
            "video_size": f"{width}x{height}",
            "framerate": "30",
            "input_format": "mjpeg",
        }

        if not os.path.exists(self.device):
            raise Exception(f"Camera {label} ({index}) not found at {self.device}")

        self.player: MediaPlayer | None = None
        self._opened = False
        self._lock = asyncio.Lock()

    async def _open_player(self):
        """
        Attempt to open the camera, retrying indefinitely until success.
        Also validates the first frame to avoid dead streams.
        """
        async with self._lock:
            while not self._opened:
                # Clean up any previous player
                if self.player:
                    self.logger.debug(f"[{self.label}] Cleaning up old player")
                    try:
                        self.player = None
                    except Exception as e:
                        self.logger.warning(f"[{self.label}] Error cleaning old player: {e}")

                # Forcefully release /dev/videoX
                self._release_device_if_busy()

                try:
                    subprocess.run([
                        "v4l2-ctl",
                        "-d", self.device,
                        f"--set-fmt-video=width={self.width},height={self.height},pixelformat=MJPG"
                    ], check=False)

                    self.logger.info(f"[{self.label}] Attempting to open {self.device}")
                    self.player = MediaPlayer(self.device, format="v4l2", options=self.options)

                    # Check first frame is valid
                    frame = await asyncio.wait_for(self.player.video.recv(), timeout=self.FIRST_FRAME_TIMEOUT)
                    if frame is None or frame.to_ndarray().size == 0:
                        raise Exception("Received empty frame, retrying")

                    self._opened = True
                    self.logger.info(f"[{self.label}] Camera opened successfully")
                    return

                except Exception as e:
                    self.logger.warning(f"[{self.label}] Failed to open camera: {e}. Retrying in {self.RETRY_INTERVAL}s")
                    await asyncio.sleep(self.RETRY_INTERVAL)

    def _release_device_if_busy(self):
        subprocess.run(["fuser", "-k", self.device], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def recv(self) -> VideoFrame:
        """
        Return the next video frame from the camera.
        Opens the player if not already opened.
        """
        if not self._opened:
            await self._open_player()

        if not self.player or not self.player.video:
            self.logger.warning(f"[{self.label}] No video track available, retrying player")
            self._opened = False
            await self._open_player()

        try:
            frame = await self.player.video.recv()
            if frame is None or frame.to_ndarray().size == 0:
                self.logger.warning(f"[{self.label}] Received empty frame, reopening camera")
                self._opened = False
                await self._open_player()
                frame = await self.player.video.recv()
            return frame
        except Exception as e:
            self.logger.warning(f"[{self.label}] Error receiving frame: {e}. Reopening camera")
            self._opened = False
            await self._open_player()
            return await self.player.video.recv()

    def stop(self):
        try:
            if self.player:
                self.player.video.stop()
                self.player.audio and self.player.audio.stop()
        except Exception:
            pass