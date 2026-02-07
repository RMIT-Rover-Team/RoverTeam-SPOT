import os
import asyncio
import logging
import subprocess
import time
from aiortc import VideoStreamTrack
from aiortc.contrib.media import MediaPlayer


class V4L2CameraTrack(VideoStreamTrack):
    WIDTH = 640
    HEIGHT = 480
    FPS = 30

    RETRY_DELAY = 2
    MAX_RETRIES = 10

    def __init__(self, index: int, label: str, logger: logging.Logger):
        super().__init__()

        self.index = index
        self.label = label
        self.logger = logger
        self.device = f"/dev/video{index}"

        if not os.path.exists(self.device):
            raise RuntimeError(f"{self.device} not found")

        self.player = None

    # --------------------------------------------------

    def _nuke_device(self):
        self.logger.warning(f"[{self.label}] Forcing device release")

        subprocess.run(["fuser", "-k", self.device],
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

        subprocess.run(["pkill", "-9", "ffmpeg"],
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

        time.sleep(0.3)

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

    # --------------------------------------------------

    def _open_player(self):
        self._nuke_device()
        self._force_mjpeg()

        options = {
            "input_format": "mjpeg",
            "framerate": str(self.FPS),
            "video_size": f"{self.WIDTH}x{self.HEIGHT}",
        }

        self.logger.info(f"[{self.label}] Opening MJPEG stream")

        self.player = MediaPlayer(
            self.device,
            format="v4l2",
            options=options,
        )

        # Hard validate format (prevents silent breakage)
        stream = self.player.video._container.streams.video[0]
        pix = stream.codec_context.pix_fmt

        if "mjpeg" not in pix.lower():
            raise RuntimeError(f"Camera returned {pix} instead of MJPEG")

    # --------------------------------------------------

    async def recv(self):
        attempts = 0

        while True:
            try:
                if not self.player:
                    self._open_player()

                frame = await self.player.video.recv()
                return frame

            except Exception as e:
                attempts += 1
                self.logger.warning(
                    f"[{self.label}] Camera error: {e} (attempt {attempts})"
                )

                self._cleanup()

                if attempts >= self.MAX_RETRIES:
                    raise RuntimeError(f"{self.label} failed permanently")

                await asyncio.sleep(self.RETRY_DELAY)

    # --------------------------------------------------

    def _cleanup(self):
        try:
            if self.player:
                try:
                    self.player.video.stop()
                except Exception:
                    pass
        finally:
            self.player = None

    # --------------------------------------------------

    def stop(self):
        self._cleanup()
        super().stop()