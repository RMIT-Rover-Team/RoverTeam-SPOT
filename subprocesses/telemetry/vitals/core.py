from typing import Dict, Any
import time
from .cpu import cpu_vitals
from .memory import memory_vitals

def collect_vitals() -> Dict[str, Any]:
    vitals = {}

    vitals["timestamp"] = time.time()
    vitals["cpu"] = cpu_vitals()
    vitals["memory"] = memory_vitals()

    return vitals
