import os
import asyncio
from aiortc import VideoStreamTrack, MediaStreamError
import logging
import subprocess
import time
import io
import av

class V4L2CameraTrack(VideoStreamTrack):
    WIDTH = 640
    HEIGHT = 480
    FPS = 30

    RETRY_DELAY = 2
    MAX_RETRIES = 10
    def __init__(self, index: int, label: str, logger: logging.Logger, width: int, height: int):
        super().__init__()
        self.index = index
        self.label = label
        self.logger = logger
        self.device = f"/dev/video{index}"

        self.WIDTH = width
        self.HEIGHT = height

        self._open_device()

        if not os.path.exists(self.device):
            raise RuntimeError(f"{self.device} not found")

        # File handle for raw capture
        self._fd = None

    # --------------------------------------------------

    def _force_mjpeg(self):
        subprocess.run(
            [
                "v4l2-ctl",
                "-d", self.device,
                f"--set-fmt-video=width={self.WIDTH},height={self.HEIGHT},pixelformat=MJPG"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        subprocess.run(
            ["v4l2-ctl", "-d", self.device, f"--set-parm={self.FPS}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def _nuke_device(self):
        pass
    # --------------------------------------------------

    def _open_device(self):
        self._force_mjpeg()
        self.logger.info(f"[{self.label}] Device ready at {self.WIDTH}x{self.HEIGHT} @ {self.FPS} FPS")

        # Open the device file for reading frames (raw MJPEG)
        self._fd = os.open(self.device, os.O_RDONLY)
        self.logger.info(f"[{self.label}] Device ready at {self.WIDTH}x{self.HEIGHT}")

    # --------------------------------------------------

    async def recv(self):
        attempts = 0
        try:
            if self._fd is None:
                raise MediaStreamError
            chunk = os.read(self._fd, 1024 * 1024)
            if not chunk:
                raise MediaStreamError("empty read")
            # MJPEG frames start with FF D8 and end with FF D9
            start = chunk.find(b"\xff\xd8")
            end   = chunk.find(b"\xff\xd9")

            if start == -1 or end == -1:
                # Not a full frame yet — try again next recv()
                return MediaStreamError("Incomplete MJPEG frame")

            jpeg = chunk[start:end+2]

            container = av.open(io.BytesIO(jpeg), format="mjpeg")
            frame = list(container.decode(video=0))
           
            if not frames:
                raise MediaStreamError("No frame decoded")
            self._pts += 1
            frame.pts = self._pts
            frame.time_base = 1 / self.FPS

            return frame

        except MediaStreamError as e:
            self.logger.error(f"[{self.label}] Camera error: {e}")
            self.stop()
            raise

        except Exception as e:
            self.logger.error(f"[{self.label}] Camera error: {e}")
            self.stop()
            raise MediaStreamError("unhandled camera error") from e

    # --------------------------------------------------

    def _cleanup(self):
        try:
            if self._fd:
                try:
                    self._fd.close()
                except Exception:
                    pass
        finally:
            self._fd = None

    # --------------------------------------------------

    def stop(self):
        self._cleanup()
