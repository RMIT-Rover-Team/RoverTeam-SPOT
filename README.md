# First Time Installation
The following guide is for the first-time installation on a Linux system.

Start by ensuring you have all of the required dependencies installed:

## Install Poetry
Ensure you have Poetry installed on your machine:
```bash
sudo curl -sSL https://install.python-poetry.org | python3
```
And add it to your `PATH` in your `.bashrc` file:
```bash
export PATH="/home/<your username>/.local/bin:$PATH"
```
You can test it has installed correctly:
```bash
poetry --version
```

## Install V4L Utilities
V4L Utilities is required to scan for available cameras on linux machines. This is only required if you intend on using the 'cameras' subprocess.
```bash
sudo apt install v4l-utils
```

## Clone the Repository
If you are familiar with Git, this isn't too tricky, however since this is a private repo, you may find it easier to download as a `.zip` file.

If you download this as a `.zip`, be aware that you'll need to re-install the entire package each time you want to update.

Do not download as a `.zip` if you intend on making and publishing changes to this project.

## Setup Virtual Environment
Poetry makes it easy to setup the virtual environment on Linux machines, and handles all of the Python dependencies.

To set up the venv, run the following in the project root:
```bash
poetry install
```

# Using SPOT
## Run the python script
To run SPOT, use the following command (requires Poetry):
```bash
poetry run python main.py
```
This ensures the correct venv is used.

## Connect to telemetry
You can connect to the various telemetry services SPOT offers through a telemetry client.

The `@RMIT-Rover-Team/RoverTeam-GUI` Github project is currently the preferred client whcih supports SPOT telemetry.

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
Since each subprocess is spawned seperately, the process.py acts as a standalone python file.

This means you are able to use custom libraries to seperate code sections and keep your code readable and concise.

For example, the telemetry process has a `vitals/` folder containing a `__init__.py` along with other helper scripts which can contain functions and classes.

This system gives full control and flexibility to any subprocess, whilst keeping required segmentation for smooth operation. 
