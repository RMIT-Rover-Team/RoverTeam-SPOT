import asyncio
import argparse
import json
import logging
import platform
import subprocess
import re
import time

import zmq
import zmq.asyncio

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
import cv2


# -------------------------
# LOGGING (JSON ONLY)
# -------------------------
class JsonHandler(logging.StreamHandler):
    def emit(self, record):
        log_obj = {
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        print(json.dumps(log_obj), flush=True)


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(JsonHandler())


# -------------------------
# CONFIG
# -------------------------
IS_WINDOWS = platform.system() == "Windows"

ZMQ_RECEIVE = False # No need to receive ZMQ commands in this process

pcs = set()
players = {}


# -------------------------
# ZMQ RECEIVE LOOP
# -------------------------
async def receive_loop(sub_socket):
    while ZMQ_RECEIVE:
        try:
            msg = await sub_socket.recv_string(flags=zmq.NOBLOCK)
            logger.warning(f"ZMQ RX: {msg}")
        except zmq.Again:
            await asyncio.sleep(0.01)


# -------------------------
# HEARTBEAT
# -------------------------
async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT", flush=True)
        await asyncio.sleep(interval)


# -------------------------
# CAMERA DISCOVERY (WINDOWS)
# -------------------------
def list_windows_cameras():
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-list_devices", "true",
        "-f", "dshow",
        "-i", "dummy",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.error("FFmpeg not found in PATH")
        return []

    cameras = []
    i = 0
    for line in proc.stderr.splitlines():

        if not "(video)" in line:
            continue

        match = re.search(r'"(.+)"', line)
        if match:
            if "Meta" in line:
                i+=1
                continue

            cameras.append({"id":i,"label":match.group(1)})
            i+=1

    return cameras


# -------------------------
# OPENCV TRACK
# -------------------------
class OpenCVCameraTrack(VideoStreamTrack):
    def __init__(self, index: int, width=640, height=480):
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
            raise RuntimeError(f"Failed to open camera index {index}")

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        ret, frame = self.cap.read()
        if not ret:
            raise RuntimeError("Camera read failed")

        video = VideoFrame.from_ndarray(frame, format="bgr24")
        video.pts = pts
        video.time_base = time_base
        return video

    def stop(self):
        if self.cap:
            self.cap.release()
        super().stop()


# -------------------------
# HTTP HANDLERS
# -------------------------
async def handle_cameras(request):
    cameras = list_windows_cameras()
    return web.json_response({"cameras":cameras})


async def handle_ping(request):
    return web.Response(text="pong")


async def handle_offer(request):
    params = await request.json()
    camera_id = int(params.get("camera_id", 0))

    cameras = list_windows_cameras()
    camera = next((c for c in cameras if c["id"] == camera_id), None)
    if camera is None:
        return web.Response(status=404, text="Camera not found")

    logger.info(f"Opening camera: {camera["label"]}")

    pc = RTCPeerConnection()
    pcs.add(pc)

    try:
        track = OpenCVCameraTrack(camera_id)
        players[pc] = track
        pc.addTrack(track)
    except Exception as e:
        logger.error(f"Failed to open camera: {e}")
        return web.Response(status=500, text=str(e))

    @pc.on("connectionstatechange")
    async def on_state():
        if pc.connectionState in ("failed", "closed"):
            await cleanup_pc(pc)

    offer = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"],
    )

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    })

# -------------------------
# CORS
# -------------------------
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        return web.Response(
            status=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": request.headers.get(
                    "Access-Control-Request-Headers", "*"
                ),
            },
        )

    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# -------------------------
# CLEANUP
# -------------------------
async def cleanup_pc(pc):
    track = players.pop(pc, None)
    if track:
        try:
            track.stop()
        except Exception:
            pass

    await pc.close()
    pcs.discard(pc)


async def on_shutdown(app):
    await asyncio.gather(*(cleanup_pc(pc) for pc in list(pcs)))


# -------------------------
# WEBRTC SERVER TASK
# -------------------------
async def webrtc_server_task(host: str, port: int):
    if not IS_WINDOWS:
        raise RuntimeError("This process is Windows-only")

    app = web.Application(
        middlewares=[cors_middleware]
    )
    app.router.add_get("/cameras", handle_cameras)
    app.router.add_post("/offer", handle_offer)
    app.router.add_get("/ping", handle_ping)
    app.on_shutdown.append(on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logger.warning(f"WebRTC camera server listening on {host}:{port}")

    while True:
        await asyncio.sleep(3600)


# -------------------------
# MAIN
# -------------------------
async def main(heartbeat_interval: float, sub_url: str, host: str, port: int):
    ctx = zmq.asyncio.Context()
    sub_socket = ctx.socket(zmq.SUB)
    sub_socket.connect(sub_url)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    tasks = [
        asyncio.create_task(receive_loop(sub_socket)),
        asyncio.create_task(heartbeat_loop(heartbeat_interval)),
        asyncio.create_task(webrtc_server_task(host, port)),
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutdown received, cancelling tasks")
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.sleep(0)


# -------------------------
# ENTRYPOINT
# -------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=float, default=5.0)
    parser.add_argument("--sub_url", type=str, default="tcp://127.0.0.1:5555")
    parser.add_argument("--webrtc_host", type=str, default="0.0.0.0")
    parser.add_argument("--webrtc_port", type=int, default=3002)
    args = parser.parse_args()

    asyncio.run(main(args.heartbeat, args.sub_url, args.webrtc_host, args.webrtc_port))