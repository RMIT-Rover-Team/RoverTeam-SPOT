import os

def get_git_info():
    git_dir = os.path.join(os.getcwd(), ".git")
    if not os.path.exists(git_dir):
        return None, None  # no git info available

    head_path = os.path.join(git_dir, "HEAD")
    try:
        with open(head_path, "r") as f:
            head = f.read().strip()

        branch = None
        commit = None

        if head.startswith("ref:"):
            # e.g., ref: refs/heads/main
            ref_path = head.split(" ")[1]
            branch = "/".join(ref_path.split("/")[2:])
            commit_path = os.path.join(git_dir, ref_path)
            if os.path.exists(commit_path):
                with open(commit_path, "r") as cf:
                    commit = cf.read().strip()
        else:
            # detached HEAD
            commit = head

        return branch, commit
    except Exception:
        return None, None
        

async def send_startup_message(send):
    branch, commit = get_git_info()
    branch_text = branch or "unknown"
    commit_text = commit[:7] if commit else "unknown"

    await send("CLEARSCREEN")
    await send("INFO Starting...")
    await send(f"SUCCESS {branch_text} @ {commit_text}")
    await send("WARNING \n   _______  ____  ______")
    await send("WARNING   / __/ _ \\/ __ \\/_  __/")
    await send("WARNING  _\\ \\/ ___/ /_/ / / /")
    await send("WARNING /___/_/   \\____/ /_/")  
    await send("WARNING SOFTWARE PLATFORM for")
    await send("WARNING ONBOARD TELEMETRY")
    await send("INFO \nDesigned for the:")
    await send("WARNING \n⣏⡉ ⡎⢱ ⡇⢸ ⡇ ⡷⣸ ⡎⢱ ⢇⡸")
    await send("WARNING ⠧⠤ ⠣⠪ ⠣⠜ ⠇ ⠇⠹ ⠣⠜ ⠇⠸")
    await send("WARNING SOFTWARE STACK\n\n")