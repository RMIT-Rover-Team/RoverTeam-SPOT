import sys

if sys.platform.startswith("win"):
    from .stream_windows import OpenCVCameraTrack as PlatformCameraTrack
elif sys.platform.startswith("linux"):
    from .stream_linux import V4L2CameraTrack as PlatformCameraTrack
else:
    PlatformCameraTrack = None  # Unsupported

async def stream_camera(camera, logger, width=640, height=480):
    """
    Returns an instance of the platform-specific camera track.
    'camera' is a dict with 'id' and 'label'
    """
    if PlatformCameraTrack is None:
        raise RuntimeError(f"Platform {sys.platform} is not supported")

    if sys.platform.startswith("win"):
        return PlatformCameraTrack(camera["id"], camera["label"], width, height)
    else:
        return PlatformCameraTrack(camera["id"], camera["label"], logger, width, height)

async def cleanup_camera(track, logger):
    if track is None:
        return

    try:
        # Windows OpenCV
        if hasattr(track, "cap") and track.cap is not None:
            track.cap.release()
            track.cap = None
            logger.debug(f"Released OpenCV camera {getattr(track, 'index', '?')}")

        # Linux MediaPlayer
        if hasattr(track, "player") and track.player is not None:
            # MediaPlayer.stop() is synchronous, but safe to await in async
            if track.player.video:
                track.player.video.stop()
            if track.player.audio:
                track.player.audio.stop()

            track.player = None
            logger.debug(f"Stopped MediaPlayer camera {getattr(track, 'index', '?')}")

        # Ensure VideoStreamTrack cleanup
        if hasattr(track, "stop"):
            track.stop()

    except Exception as e:
        logger.warning(f"Failed to cleanup camera track: {e}")