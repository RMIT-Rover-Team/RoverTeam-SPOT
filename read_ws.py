import asyncio
import websockets
import json


async def listen():
    # Make sure port matches your main script (default 8765)
    uri = "ws://0.0.0.0:5000/ws"

    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Waiting for messages...")
            while True:
                message = await websocket.recv()
                data = json.loads(message)

                # Pretty print the JSON
                print(json.dumps(data, indent=2))
    except ConnectionRefusedError:
        print("Could not connect. Is the PDB script running?")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # You might need to install websockets: pip install websockets
    asyncio.run(listen())
