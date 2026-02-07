# scan_linux_safe.py
import os
import fnmatch

def scan_linux(ignore_list=None, logger=None):
    """
    Scan Linux video devices without opening /dev/video*.
    Avoids duplicates by USB bus if possible.
    Returns list of dicts: {"id": 0, "label": "Camera Name"}
    """
    if ignore_list is None:
        ignore_list = []

    cameras = []
    seen_buses = set()

    video_path = "/dev"
    v4l_path = "/sys/class/video4linux"

    if not os.path.exists(v4l_path):
        if logger:
            logger.warning(f"{v4l_path} does not exist, no cameras found")
        return []

    for entry in sorted(os.listdir(v4l_path)):
        # entry is e.g., video0, video1
        dev_path = os.path.join(video_path, entry)
        sys_entry = os.path.join(v4l_path, entry)

        if not os.path.exists(dev_path):
            continue

        # Default label if no info is found
        label = entry

        try:
            # Attempt to read "name" file under sysfs
            name_file = os.path.join(sys_entry, "name")
            if os.path.exists(name_file):
                with open(name_file, "r") as f:
                    label = f.read().strip()

            # Attempt to read USB bus info to skip duplicates
            # Usually symlink ../../../../usbX/Y-Z
            device_link = os.path.realpath(os.path.join(sys_entry, "device"))
            bus_info = os.path.basename(device_link) if device_link else None

        except Exception as e:
            if logger:
                logger.debug(f"Failed reading sysfs for {dev_path}: {e}")
            bus_info = None

        # Skip ignore-list items
        if any(fnmatch.fnmatch(label, pattern) for pattern in ignore_list):
            continue

        # Skip duplicates by bus
        if bus_info and bus_info in seen_buses:
            if logger:
                logger.debug(f"Skipping {dev_path}: duplicate bus {bus_info}")
            continue

        cameras.append({"id": int(entry[5:]), "label": label})
        if bus_info:
            seen_buses.add(bus_info)

        if logger:
            logger.debug(f"Detected camera: {dev_path} -> {label}")

    return cameras