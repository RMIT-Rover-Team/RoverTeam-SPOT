import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame
import asyncio

class OpenCVCameraTrack(VideoStreamTrack):
    def __init__(self, index: int, label: str, width=640, height=480):
        super().__init__()
        self.index = index
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*"MJPG"),
        )

        if not self.cap.isOpened():
            raise Exception(f"'{label}' ({index}). Consider adding this to --ignore_cameras.")

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            raise Exception("Camera read failed")

        video = VideoFrame.from_ndarray(frame, format="bgr24")
        video.pts = pts
        video.time_base = time_base
        return video

    def stop(self):
        if self.cap:
            self.cap.release()
        super().stop()