import asyncio
import sys
from supervisor.core import Supervisor

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    supervisor = Supervisor(loop=loop)

    try:
        loop.run_until_complete(supervisor.start())
    except KeyboardInterrupt:
        loop.run_until_complete(supervisor.shutdown())
    finally:
        loop.close()
        print("Exited cleanly.")

if __name__ == "__main__":
    main()