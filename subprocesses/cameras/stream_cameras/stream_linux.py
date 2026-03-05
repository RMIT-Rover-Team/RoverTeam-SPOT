import os
import asyncio
import logging
import subprocess
import time

class V4L2CameraTrack:
    WIDTH = 640
    HEIGHT = 480
    FPS = 30

    RETRY_DELAY = 2
    MAX_RETRIES = 10

    def __init__(self, index: int, label: str, logger: logging.Logger, width: int, height: int):
        self.index = index
        self.label = label
        self.logger = logger
        self.device = f"/dev/video{index}"

        self.WIDTH = width
        self.HEIGHT = height

        if not os.path.exists(self.device):
            raise RuntimeError(f"{self.device} not found")

        # File handle for raw capture
        self._fd = None

    # --------------------------------------------------

    def _nuke_device(self):
        self.logger.warning(f"[{self.label}] Forcing device release")

        subprocess.run(["fuser", "-k", self.device],
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

    def _open_device(self):
        self._nuke_device()
        self._force_mjpeg()
        self.logger.info(f"[{self.label}] Device ready at {self.WIDTH}x{self.HEIGHT} @ {self.FPS} FPS")

        # Open the device file for reading frames (raw MJPEG)
        self._fd = open(self.device, "rb", buffering=0)

    # --------------------------------------------------

    async def recv(self):
        attempts = 0

        while True:
            try:
                if not self._fd:
                    self._open_device()

                # Read a single MJPEG frame from the device
                # NOTE: adjust size if necessary or use a proper MJPEG parser
                # Here we just read raw bytes
                frame = self._fd.read(self.WIDTH * self.HEIGHT * 3)  # rough placeholder

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