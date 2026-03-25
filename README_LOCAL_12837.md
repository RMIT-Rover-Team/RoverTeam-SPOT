# Introduction
The ***Software Platform* for *Onboard Telemetry*** is a multi-process operating environment designed for the RMIT Rover Team's **Equinox** Rover and it's corresponding ***Equinox Software Stack*** which run across 2 independent Raspberry Pi 4B (8GB) Single-Board Computers.
 
The following guide is for first-time installation of the SPOT operating system. We recommend using a Linux based OS for hosting a SPOT instance, however limited Windows support is still available for development and testing requirements. The following platforms are currently supported, tested, and validated:
| OS | Support| Testing & Validation* |
|----|--------|----------------------|
| ![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-C51A4A?logo=raspberrypi&logoColor=white) |![Full Support](https://img.shields.io/badge/Full%20Support-00AA00) | ✅ Production Ready |
![Linux](https://img.shields.io/badge/Linux%20%28Debian%20Based%29-FCC624?logo=linux&logoColor=000000)  | ![Full Support](https://img.shields.io/badge/Full%20Support-00AA00) | ⬜ Development Only |
![Windows](https://img.shields.io/badge/⊞%20Windows-0078D6?logo=windows&logoColor=white) | ![Limited Support](https://img.shields.io/badge/Limited%20Support-FF8800) | ⬜ Development Only |
![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white) |![Not Supported](https://img.shields.io/badge/Not%20Supported-AA0000) |  ⬜ N/A |

*Testing and Validation requirements are only applicable for the `main` branch. Do not use the `/dev` branch or any other branch for deployment purposes.


# Installation
To get started, ensure your platform is supported on the above table. Note that only Debian based distributions of Linux are currently supported under the 'Linux' tag. This includes Ubuntu and Linux Mint.

As mentioned above, Windows support is very limited, and was mainly introduced as a measure to allow for the development of the GUI client. This includes support for Cameras and Telemetry, but lacks any features relating to CAN Bus or peripheral support outside of cameras.

To get started, ensure you have all of the required dependencies installed:

## Install Poetry  ![Required](https://img.shields.io/badge/REQUIRED-AA0000)
SPOT uses Poetry to manage virtual environments and pip requirements.

**Ensure you have Poetry installed on your machine:**

![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black) ![RPI](https://img.shields.io/badge/Raspberry%20PI-A22846?style=for-the-badge&logo=raspberrypi&logoColor=white)
```bash
sudo curl -sSL https://install.python-poetry.org | python3
```
After installation, check if Poetry was automatically added to the PATH:
```bash
poetry --version
```
If this works, you can skip the following. Otherwise, you'll need to add it to the path manually through the `.bashrc` file:

The `.bashrc` file should be located in your home directory:
```bash
sudo nano ~/.bashrc
```
And add the following line to the file:
```bash
export PATH="/home/<your username>/.local/bin:$PATH"
```
Then load the changes into your current terminal session:
```bash
source ~/.bashrc
```
Then you can test it has installed correctly:
```bash
poetry --version
```

**OR:**

![Windows](https://img.shields.io/badge/⊞%20Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
Open a new PowerShell terminal with Administrator privileges (run as administrator) and run the following:
```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
```
You can test it has installed correctly:
```powershell
poetry --version
```
If this doesn't work, you'll need to add it to your PATH system environment manually. and try again.

## Install V4L Utilities ![Optional](https://img.shields.io/badge/OPTIONAL-FF8800)
V4L Utilities is used to scan for available cameras on Linux machines. It is recommended you install this if using Linux or Raspberry Pi OS in order to have full camera functionality. This is installed by default on many operating systems.

![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black) ![RPI](https://img.shields.io/badge/Raspberry%20PI-A22846?style=for-the-badge&logo=raspberrypi&logoColor=white)
```bash
sudo apt install v4l-utils
```

## Install FFmpeg ![Optional](https://img.shields.io/badge/OPTIONAL-FF8800)
FFmpeg is used to scan for available cameras on Windows machines. This is only required if you intend on using the 'cameras' subprocess on a Windows device.

![Windows](https://img.shields.io/badge/⊞%20Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
Go to the following website and follow the installation instructions for the Windows operating system:
https://www.ffmpeg.org/download.html

## Clone the Repository
If you are familiar with Git, this is self a explanatory step. If you are using the `git` command-line interface, in a folder of your choice (we recommend your `home` directory):
```bash
git clone https://github.com/RMIT-Rover-Team/RoverTeam-SPOT.git
```
And use a branch of choice. The `dev` branch contains the most up-to-date code, however it can also include instabilities. The `main` branch will contain tested and reliable code revisions. If you want to use the `main` branch, you can skip this step, otherwise pull the desired branch, for example:
```bash
cd RoverTeam-SPOT
git pull origin dev
```


## Setup Virtual Environment
Poetry makes it easy to setup the virtual environment on Linux machines, and handles all of the Python dependencies.

To set up the venv, run the following in the repo folder:
```bash
poetry install
```

# Getting Started
## Run the python script
To run SPOT, use the following command (requires Poetry):
```bash
poetry run python main.py
```
This ensures the correct venv is used.

## Connect to telemetry
You can connect to the various telemetry services SPOT offers through a telemetry client.

The `@RMIT-Rover-Team/RoverTeam-GUI` GitHub project is currently the preferred client which supports SPOT telemetry. You can view the repo [here](https://github.com/RMIT-Rover-Team/RoverTeam-GUI/).

It runs a React/Next.js front-end which is capable of establishing connections to SPOT for streaming both telemetry data, as well as camera and peripheral data. More information is available on that repo.

The following commands are built-in to the telemetry/supervisor stack:
```bash
> start <process>
> stop <process>
> restart <process>
```

More on processes and how to use/create them can be found in the next section

# Using SPOT Subprocesses
SPOT relies on subprocesses to manage tasks. This ensures that processes are segregated, and can error or break without affecting the rest of the system.

## File Heirarchy
All subprocesses are stored under the `subprocesses/` folder with the following heirarchy:

```
subprocesses/
├─ my_process/
|  ├─ process.py
|  ├─ config.json5
|  └─ some_lib/
...
```

## `config.json5`
Each process has a config file written in JSON5. This is backwards-compatable with regular JSON, but has support for comments and additional quality-of-life improvements.

The following schema can be used for a config file:

```json5
{
    "name": "template",
    "priority": -1,
    "args": {
        "--some_string": "string",
        "--some_number": 67,
        "--some_list": [
            "el1",
            "el2"
        ]
    }
}
```

### `name`
The display name of the subprocess. We recommend keeping this the same as the folder name.

This cannot contain spaces or weird characters - keep it to lowercase and maybe an underscore if you have to.

Simple 1-word names are preferred.

### `priority`
LOWER numbers have HIGHER priority
+ `-1`: ignored (templates, temp., etc.)
+ `0-9`: TIER 1 = critical items
+ `10-99`: TIER 2 = standard, non-breaking items
+ `100+`: TIER 3 = experimental, low-priority

### `args`
These are args that are called on the subprocess and retrieved by `process.py`.
This is where your per-process custom configurations can go.

## `process.py`
This is the main entry-point for a process.

every process has strict rules which must be followed for them to run smoothly.

### Heartbeat
Every process must have a heartbeat which allows the supervisor to determine the process is 'alive'

If a heartbeat fails to receive after a determined grace-period, the supervisor will attempt to restart the process.

A heartbeat task can look like this:
```python
# Use asyncio.create_task() to spawn this
async def heartbeat_loop(interval: float):
    while True:
        print("HEARTBEAT")
        await asyncio.sleep(interval)
```

Be aware that the supervisor will automatically attach a `--heartbeat` argument to every process, containing a `float` which is the interval (in seconds) of which it expects a heartbeat.

## Additional Libraries
Since each subprocess is spawned separately, the process.py acts as a standalone python file.

This means you are able to use custom libraries to separate code sections and keep your code readable and concise.

For example, the telemetry process has a `vitals/` folder containing a `__init__.py` along with other helper scripts which can contain functions and classes.

This system gives full control and flexibility to any subprocess, whilst keeping required segmentation for smooth operation. 

If you are using a pip library, ensure you add it using Poetry. For example:
```bash
poetry add some-pip-library
```
