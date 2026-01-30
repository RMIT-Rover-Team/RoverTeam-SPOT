# scan_linux.py
import subprocess
import os

def scan_linux(ignore_list=None, logger=None):
    """
    Scan Linux /dev/video* devices using v4l2-ctl, avoiding duplicates by bus when possible.

    If device info cannot be read, include it anyway with label=path.
    """
    if ignore_list is None:
        ignore_list = []

    cameras = []
    seen_buses = set()

    for dev in sorted(os.listdir("/dev")):
        if not dev.startswith("video"):
            continue

        path = f"/dev/{dev}"
        if path in ignore_list:
            continue

        card = None
        bus = None

        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", path, "--info"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout + "\n" + result.stderr

            for line in output.splitlines():
                line = line.strip()
                if line.lower().startswith("card type"):
                    card = line.split(":", 1)[1].strip()
                elif line.lower().startswith("bus info"):
                    bus = line.split(":", 1)[1].strip()

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            if logger:
                logger.debug(f"Could not run v4l2-ctl on {path}: {e}")

        # If parsing failed, just use the path as the label
        label = card if card else path

        # Skip duplicates only if bus info is available
        if bus and bus in seen_buses:
            if logger:
                logger.debug(f"Skipping {path}: duplicate bus {bus}")
            continue

        cameras.append({"id": int(dev[5:]), "label": label})
        if bus:
            seen_buses.add(bus)

        if logger:
            logger.debug(f"Detected camera: {path} -> {label}")

    return cameras