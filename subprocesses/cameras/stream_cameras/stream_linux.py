import os
import logging
import asyncio
import subprocess
from aiortc import VideoStreamTrack
from aiortc.contrib.media import MediaPlayer

class V4L2CameraTrack(VideoStreamTrack):
    """
    Linux V4L2 camera track with robust device handling:
    - Forcefully releases /dev/videoX if busy
    - Retries opening MediaPlayer if fails
    - Detects stuck frames and auto-restarts
    - Cleans up properly on stop
    """

    MAX_RETRIES = 5       # Max attempts to open the camera
    RETRY_DELAY = 1       # Seconds between attempts
    STUCK_TIMEOUT = 2.0   # Seconds to detect a stuck frame

    def __init__(self, index: int, label: str, logger: logging.Logger, width=640, height=480):
        super().__init__()
        self.index = index
        self.label = label
        self.logger = logger
        self.device = f"/dev/video{index}"
        self.width = width
        self.height = height

        if not os.path.exists(self.device):
            raise Exception(f"Camera {label} ({index}) not found at {self.device}")

        self.player: MediaPlayer | None = None
        self.options = {
            "format": "v4l2",
            "video_size": f"{width}x{height}",
            "framerate": "30",
            "input_format": "mjpeg",
        }

        self._release_device_if_busy()  # still safe in constructor
        self._player_open_lock = asyncio.Lock()  # prevent multiple concurrent opens

    async def _open_player(self):
        async with self._player_open_lock:
            if self.player is not None:
                return  # already open

            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    self.player = MediaPlayer(self.device, format="v4l2", options=self.options)
                    self.logger.info(f"Camera {self.label} opened successfully on attempt {attempt}")
                    return
                except Exception as e:
                    self.logger.warning(f"[Attempt {attempt}] Failed to open camera {self.label}: {e}")
                    if attempt == self.MAX_RETRIES:
                        raise Exception(f"Failed to open camera {self.label} after {self.MAX_RETRIES} attempts")
                    await asyncio.sleep(self.RETRY_DELAY)

    async def recv(self):
        # make sure player is open before receiving frames
        if self.player is None:
            await self._open_player()

        if not hasattr(self.player, "video") or self.player.video is None:
            self.logger.warning(f"No video track available from {self.label}")
            raise asyncio.CancelledError()

        try:
            frame = await asyncio.wait_for(self.player.video.recv(), timeout=self.STUCK_TIMEOUT)
            return frame
        except asyncio.TimeoutError:
            self.logger.warning(f"Camera {self.label} appears stuck. Restarting MediaPlayer.")
            await self._restart_player()
            raise asyncio.CancelledError()

    def _release_device_if_busy(self):
        """Kill any processes using /dev/videoX to free the device."""
        try:
            # fuser method
            result = subprocess.run(["fuser", "-v", self.device], capture_output=True, text=True)
            lines = result.stdout.splitlines()
            pids = []
            for line in lines[1:]:
                parts = line.split()
                if parts and parts[0].isdigit():
                    pids.append(int(parts[0]))
            for pid in pids:
                try:
                    os.kill(pid, 9)
                    self.logger.warning(f"Killed process {pid} using {self.device}")
                except Exception as e:
                    self.logger.warning(f"Failed to kill PID {pid}: {e}")

            # additional check for lingering ffmpeg/v4l2-ctl processes
            extra = subprocess.run(["pgrep", "-f", self.device], capture_output=True, text=True)
            for pid_str in extra.stdout.splitlines():
                if pid_str.isdigit():
                    pid = int(pid_str)
                    try:
                        os.kill(pid, 9)
                        self.logger.warning(f"Killed extra process {pid} using {self.device}")
                    except Exception as e:
                        self.logger.warning(f"Failed to kill extra PID {pid}: {e}")

        except FileNotFoundError:
            self.logger.warning("fuser command not found, cannot forcefully release camera")
        except Exception as e:
            self.logger.warning(f"Error checking camera device {self.device}: {e}")

    async def _restart_player(self):
        """Stop and re-open the MediaPlayer if frames get stuck."""
        self.stop()
        self._release_device_if_busy()
        await self._open_player()

    def stop(self):
        """
        Safely stop the camera track and release resources.
        """
        try:
            if self.player:
                # terminate ffmpeg process if exists
                if hasattr(self.player, "_process") and self.player._process:
                    self.player._process.kill()
                self.player = None
        except Exception as e:
            self.logger.warning(f"Error stopping camera {self.label}: {e}")
        super().stop()