import os
import logging
import asyncio
import subprocess
from aiortc import VideoStreamTrack
from aiortc.contrib.media import MediaPlayer

class V4L2CameraTrack(VideoStreamTrack):
    """
    Linux V4L2 camera track that forcibly releases /dev/videoX if busy.
    """
    def __init__(self, index: int, label: str, logger: logging.Logger, width=640, height=480):
        super().__init__()
        self.index = index
        self.logger = logger
        self.device = f"/dev/video{index}"

        if not os.path.exists(self.device):
            raise Exception(f"Camera {label} ({index}) not found at {self.device}")

        # Forcefully release /dev/video if busy
        self._release_device_if_busy(label)

        options = {
            "format": "v4l2",
            "video_size": f"{width}x{height}",
            "framerate": "30",
            "input_format": "mjpeg",
        }

        try:
            self.player = MediaPlayer(self.device, format="v4l2", options=options)
        except Exception as e:
            raise Exception(f"Failed to open camera {label} ({index}): {e}")

    def _release_device_if_busy(self, label: str):
        """
        Kill any processes using /dev/videoX to free the device.
        """
        try:
            # fuser outputs PIDs of processes using the device
            result = subprocess.run(["fuser", "-v", self.device],
                                    capture_output=True, text=True)
            lines = result.stdout.splitlines()
            if len(lines) > 1:
                # There are processes using the device
                pids = []
                for line in lines[1:]:
                    parts = line.split()
                    if parts:
                        pid = parts[0]
                        if pid.isdigit():
                            pids.append(int(pid))
                if pids:
                    self.logger.warning(f"Camera {label} busy, killing processes: {pids}")
                    for pid in pids:
                        try:
                            os.kill(pid, 9)
                        except Exception as e:
                            self.logger.warning(f"Failed to kill PID {pid}: {e}")
        except FileNotFoundError:
            # fuser not installed
            self.logger.warning("fuser command not found, cannot forcefully release camera")
        except Exception as e:
            self.logger.warning(f"Error checking camera device: {e}")

    async def recv(self):
        if not hasattr(self.player, "video") or self.player.video is None:
            self.logger.warning("No video track available from MediaPlayer")
            raise asyncio.CancelledError()

        frame = await self.player.video.recv()
        return frame

    def stop(self):
        if hasattr(self, "player") and self.player:
            self.player.stop()
        super().stop()