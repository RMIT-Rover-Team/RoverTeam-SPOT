import sys

from .stream_linux import CameraBroadcaster, SharedCameraTrack

# Global dictionary to hold our running broadcasters
ACTIVE_BROADCASTERS = {}


async def stream_camera(camera, logger, width=640, height=480):
    device_id = camera["id"]

    device_label = camera["label"]
    useSize = True

    if "USB2.0 UVC PC Camera: USB2.0 UV" in device_label:
        logger.warning("NOT USING SIZE - I THINK THIS IS MICROSCOPE!!!")
        useSize = False

    # If the broadcaster is physically dead, clear it out
    if device_id in ACTIVE_BROADCASTERS:
        b = ACTIVE_BROADCASTERS[device_id]
        if not b.running or b.error:
            logger.warning(f"Broadcaster for camera {device_id} is dead. Cleaning up.")
            b.stop()
            del ACTIVE_BROADCASTERS[device_id]

    # Create/start it if it doesn't exist
    if device_id not in ACTIVE_BROADCASTERS:
        if sys.platform.startswith("linux"):
            device_path = f"/dev/video{device_id}"
            broadcaster = CameraBroadcaster(device_path, width, height, logger, useSize)
            logger.info("created camera instance")
            logger.info(len(ACTIVE_BROADCASTERS))
        else:
            raise RuntimeError(f"Platform {sys.platform} is not supported")

        broadcaster.start()
        ACTIVE_BROADCASTERS[device_id] = broadcaster

    broadcaster = ACTIVE_BROADCASTERS[device_id]
    broadcaster.clients += 1

    track = SharedCameraTrack(broadcaster)
    track.device_id = device_id
    return track


async def cleanup_camera(track, logger):
    if not track:
        return

    # Decrement clients for shared broadcast
    if isinstance(track, SharedCameraTrack):
        broadcaster = track.broadcaster
        broadcaster.clients -= 1

        # If last viewer left, physically turn off camera
        if broadcaster.clients <= 0:
            broadcaster.stop()

            keys_to_delete = [
                k for k, v in ACTIVE_BROADCASTERS.items() if v == broadcaster
            ]
            for k in keys_to_delete:
                del ACTIVE_BROADCASTERS[k]
                logger.info("Destroying broadcaster")
                logger.info(len(ACTIVE_BROADCASTERS))
            logger.info(f"Released shared camera {broadcaster.device}")

    if hasattr(track, "stop"):
        track.stop()