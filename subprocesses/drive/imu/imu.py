import asyncio
import logging
import math
import platform
import time

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"

IMU_ID = 0x5


class IMUDriver:

    def __init__(self, control_socket, *, force_sim=False):

        self.control_socket = control_socket
        self.force_sim = force_sim

        self.data = {
            "gyro_p": 0.0,
            "gyro_y": 0.0,
            "gyro_r": 0.0,
            "vel_fd": 0.0,
            "vel_up": 0.0,
            "vel_lr": 0.0,
        }

        self.simulated = force_sim or IS_WINDOWS

        self._task = None

    async def start(self):

        if self.simulated:
            log.info("IMU running in SIMULATION mode")
            self._task = asyncio.create_task(self._fake_loop())
        else:
            log.info("IMU running in REAL CAN mode")
            import sharedlib.payloadControl.pyRover as pyRover
            self.imuMaster = pyRover.PyRover("can0", 1)
            self._task = asyncio.create_task(self._can_loop())

        asyncio.create_task(self._publish_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()

    # -------------------------
    # REAL CAN IMU
    # -------------------------

    async def _can_loop(self):

        RowLookup = {0: "gyro", 1: "vel"}

        ColLookup = {
            "gyro": ["p", "y", "r"],
            "vel": ["fd", "up", "lr"],
        }

        while True:

            nextDP = self.imuMaster.BroadcastDataPoint()

            if nextDP[0]["from"] == IMU_ID:

                row = RowLookup[nextDP[0]["stream_id"]]
                col = ColLookup[row][nextDP[0]["channel_id"]]

                key = f"{row}_{col}"

                if key in self.data:
                    self.data[key] = nextDP[1]

            await asyncio.sleep(0.01)

    # -------------------------
    # SIMULATED IMU
    # -------------------------

    async def _fake_loop(self):

        start = time.time()

        while True:

            t = time.time() - start

            self.data["gyro_p"] = math.sin(t) * 30
            self.data["gyro_y"] = math.cos(t * 0.7) * 45
            self.data["gyro_r"] = math.sin(t * 0.5) * 20

            self.data["vel_fd"] = math.sin(t * 0.4)
            self.data["vel_up"] = math.cos(t * 0.6)
            self.data["vel_lr"] = math.sin(t * 0.9)

            await asyncio.sleep(0.02)

    # -------------------------
    # PUBLISH TO CONTROL SOCKET
    # -------------------------

    async def _publish_loop(self):

        while True:

            for k, v in self.data.items():
                self.control_socket.outputs.set_output(k, v)

            await asyncio.sleep(0.1)  # 10hz