import psutil

def cpu_vitals():
    return {
        "usage_percent": psutil.cpu_percent(interval=None),
        "cores_logical": psutil.cpu_count(logical=True),
        "cores_physical": psutil.cpu_count(logical=False),
        "freq_mhz": (
            psutil.cpu_freq().current
            if psutil.cpu_freq() else None
        ),
    }