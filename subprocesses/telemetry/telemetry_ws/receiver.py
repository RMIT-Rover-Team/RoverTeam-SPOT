# receiver.py
async def handle_message(message, broadcast):
    print(f"SYSTEM CMD {message}")
    await broadcast(f"SUCCESS > {message}")