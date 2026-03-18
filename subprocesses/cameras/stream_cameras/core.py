import sys


from .stream_linux import CameraBroadcaster, SharedCameraTrack

# Global dictionary to hold our running broadcasters
ACTIVE_BROADCASTERS = {}


async def stream_camera(camera, logger, width=640, height=480):
    """
    Returns an instance of the proxy camera track for a client.
    'camera' is a dict with 'id' and 'label'
    """
    device_id = camera["id"]

    # Check if the broadcaster is already running. If not, start it.
    if device_id not in ACTIVE_BROADCASTERS:
        if sys.platform.startswith("linux"):
            device_path = f"/dev/video{device_id}"
            broadcaster = CameraBroadcaster(device_path, width, height, logger)
        # elif sys.platform.startswith("win"):
        #     # You can build an identical WindowsBroadcaster using cv2.VideoCapture
        #     # inside the _capture_loop instead of PyAV!
        #     broadcaster = WindowsBroadcaster(device_id, width, height, logger)
        else:
            raise RuntimeError(f"Platform {sys.platform} is not supported")

        broadcaster.start()
        ACTIVE_BROADCASTERS[device_id] = broadcaster

    # Return a new lightweight proxy track for this specific client connection
    return SharedCameraTrack(ACTIVE_BROADCASTERS[device_id])


async def cleanup_camera(camera_id, logger):
    """
    Call this when you want to completely shut down the camera
    (e.g., when the LAST client disconnects).
    """
    broadcaster = ACTIVE_BROADCASTERS.pop(camera_id, None)
    if broadcaster:
        broadcaster.stop()
        logger.info(f"Released shared camera {camera_id}")