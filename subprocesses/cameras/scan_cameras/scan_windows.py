import subprocess
import re
import fnmatch

def scan_windows(ignore_list, logger):
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
            label = match.group(1)

            # Skip if in the ignore-list, but still increment
            if any(fnmatch.fnmatch(label, pattern) for pattern in ignore_list):
                i+=1
                continue

            cameras.append({"id":i,"label":match.group(1)})
            i+=1

    return cameras