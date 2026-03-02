import subprocess
import os
import pytest


def is_vcan_up(interface="vcan0"):
    """Check if the vcan interface already exists."""
    return os.path.exists(f"/sys/class/net/{interface}")


@pytest.fixture(scope="session", autouse=True)
def setup_vcan_interface():
    interface = "vcan0"

    if not is_vcan_up(interface):
        print(f"\n--- Setting up {interface} ---")
        try:
            # We use sudo because these are kernel/network level commands
            subprocess.run(["sudo", "modprobe", "vcan"], check=True)
            subprocess.run(
                ["sudo", "ip", "link", "add", "dev", interface, "type", "vcan"],
                check=True,
            )
            subprocess.run(["sudo", "ip", "link", "set", "up", interface], check=True)
        except subprocess.CalledProcessError as e:
            pytest.exit(f"Failed to setup vcan0: {e}. Do you have sudo privileges?")
    else:
        print(f"\n--- {interface} is already up ---")

    yield  # This is where the tests happen

    # print(f"\n--- Tearing down {interface} ---")
    # subprocess.run(["sudo", "ip", "link", "delete", interface], check=False)
