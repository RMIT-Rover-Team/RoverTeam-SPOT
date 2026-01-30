def handle_message(message, broadcast):
    print(f"SYSTEM CMD {message}")
    broadcast(f"SUCCESS > {message}")