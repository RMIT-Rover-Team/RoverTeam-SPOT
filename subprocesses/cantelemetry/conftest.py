import pytest
import subprocess
import sys
import os


@pytest.fixture(scope="session", autouse=True)
def setup_can():
    subprocess.run(["sudo", "modprobe", "vcan"])
    subprocess.run(["sudo", "ip", "link", "add", "dev", "vcan0", "type", "vcan"])
    subprocess.run(["sudo", "ip", "link", "set", "up", "vcan0"])


@pytest.fixture(scope="session", autouse=True)
def pytest_load_initial_conftests():
    sys.path = [p for p in sys.path if "/opt/ros" not in p]

    # 2. Prevent subprocesses from inheriting the "poisoned" path
    if "PYTHONPATH" in os.environ:
        ros_paths = [
            p for p in os.environ["PYTHONPATH"].split(":") if "/opt/ros" not in p
        ]
        os.environ["PYTHONPATH"] = ":".join(ros_paths)
