import logging
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel
from .startup import send_startup_message
from .cors import cors_middleware
from .receiver import handle_message 

# -------------------------
# MODULE-LEVEL STATE
# -------------------------
pcs: set[RTCPeerConnection] = set()
channels: set[RTCDataChannel] = set()

# -------------------------
# HELPERS
# -------------------------
def get_peer_count() -> int:
    return len(pcs)

def get_channel_count() -> int:
    return len(channels)

def broadcast(message: str):
    for ch in list(channels):
        if ch.readyState == "open":
            ch.send(message)

# -------------------------
# WEBRTC HANDLERS
# -------------------------
async def handle_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"]
    )

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        logging.info("Incoming WebRTC channel")
        channels.add(channel)

        send_startup_message(channel)

        @channel.on("close")
        def on_close():
            channels.discard(channel)

        @channel.on("message")
        def on_message(message):
            handle_message(message, broadcast)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

async def start_webrtc_server(host="0.0.0.0", port=3002):
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_post("/offer", handle_offer)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)

    logging.warning(f"WebRTC logging server listening on {host}:{port}")
    await site.start()
