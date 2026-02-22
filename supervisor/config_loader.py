# supervisor/config_loader.py

import json
import json5
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any

from supervisor.logging import get_logger


# ============================================================
# CONSTANTS
# ============================================================
SUBSYSTEMS_DIR = Path(__file__).parent.parent / "subprocesses"
CONFIG_FILE = Path(__file__).parent / "config.json5"

log = get_logger("config_loader")

def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json5.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load supervisor config: {e}")


# ============================================================
# DATA STRUCTURE
# ============================================================
@dataclass
class Subsystem:
    """
    Static configuration + runtime state container.
    Runtime fields will be managed by ProcessManager.
    """

    name: str
    priority_rank: int
    path: Path
    extra_args: List[str] = field(default_factory=list)

    # Runtime state (managed elsewhere)
    process: Optional[Any] = None
    last_heartbeat: float = 0.0
    restart_pending: bool = False
    intentionally_stopped: bool = False


# ============================================================
# PUBLIC API
# ============================================================
def load_subsystems() -> Dict[str, Subsystem]:
    """
    Scans the subprocesses directory and loads all valid subsystem configs.
    Returns dictionary keyed by subsystem name.
    """

    subsystems: Dict[str, Subsystem] = {}

    if not SUBSYSTEMS_DIR.exists():
        log.error(f"Subprocess directory not found: {SUBSYSTEMS_DIR}")
        return subsystems

    for folder in SUBSYSTEMS_DIR.iterdir():

        if not folder.is_dir():
            continue

        process_file = folder / "process.py"
        config_file = _find_config_file(folder)

        if not process_file.exists():
            log.warning(f"{folder.name}: missing process.py")
            continue

        if config_file is None:
            log.warning(f"{folder.name}: missing config.json or config.json5")
            continue

        cfg = _load_config(config_file)
        if cfg is None:
            continue

        name = cfg.get("name", folder.name)
        priority = cfg.get("priority", 5)
        args = cfg.get("args", {})

        if priority < 0:
            # Explicit disable mechanism
            log.info(f"{name}: disabled (priority < 0)")
            continue

        subsystem = Subsystem(
            name=name,
            priority_rank=priority,
            path=process_file,
            extra_args=flatten_args(args),
        )

        if name in subsystems:
            log.error(f"Duplicate subsystem name detected: {name}")
            continue

        subsystems[name] = subsystem

    log.info(f"Loaded subsystems: {list(subsystems.keys())}")

    return subsystems


# ============================================================
# INTERNAL HELPERS
# ============================================================
def _find_config_file(folder: Path) -> Optional[Path]:
    """
    Prefer json5, fallback to json.
    """

    json5_file = folder / "config.json5"
    json_file = folder / "config.json"

    if json5_file.exists():
        return json5_file

    if json_file.exists():
        return json_file

    return None


def _load_config(path: Path) -> Optional[dict]:
    """
    Load config file safely.
    """

    try:
        with open(path, "r", encoding="utf-8") as f:
            if path.suffix == ".json5":
                return json5.load(f)
            return json.load(f)

    except Exception as e:
        log.error(f"Failed to parse {path}: {e}")
        return None


def flatten_args(args: dict) -> List[str]:
    """
    Converts structured config args into CLI argument list.

    Example:
        {
            "--port": 5000,
            "--verbose": True,
            "--camera": [0, 1]
        }

    Becomes:
        [
            "--port", "5000",
            "--verbose",
            "--camera", "0",
            "--camera", "1"
        ]
    """

    result: List[str] = []

    for key, value in args.items():

        if value is None:
            continue

        # Boolean flag
        if isinstance(value, bool):
            if value:
                result.append(key)
            continue

        # List → repeat flag
        if isinstance(value, list):
            for item in value:
                result.append(key)
                result.append(str(item))
            continue

        # Everything else → single value
        result.append(key)
        result.append(str(value))

    return result