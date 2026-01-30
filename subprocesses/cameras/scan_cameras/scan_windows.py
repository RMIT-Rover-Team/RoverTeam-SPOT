import subprocess

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
            if match.group(1) in ignore_list:
                i+=1
                continue

            cameras.append({"id":i,"label":match.group(1)})
            i+=1

    return cameras