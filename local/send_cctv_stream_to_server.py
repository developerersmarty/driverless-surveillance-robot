#send_cctv_stream_to_server.py
# Import necessary modules for WebRTC, RTSP media playback, and HTTP requests
import asyncio
import os
from aiortc import (
    RTCPeerConnection,
    RTCConfiguration,
    RTCIceServer,
    RTCSessionDescription,
    VideoStreamTrack
)
from aiortc.contrib.media import MediaPlayer
from aiohttp import ClientSession

# === Static Configuration ===
CAMERA_IP = "192.168.0.111"  # Replace with your camera's IP
RTSP_USER = "admin"          # Replace with your RTSP/ONVIF username
RTSP_PASS = "password"       # Replace with your RTSP/ONVIF password
RTSP_PORT = "554"            # RTSP port (default is 554)
RTSP_STREAM = "stream2"      # e.g., stream1, stream2, etc (FYI - user stream2 to reduce CPU usage)

SERVER_IP = "Your Server IP Address"  # Server IP address
SERVER_PORT = "8889"         # Port for WebRTC
MediaMTX_ENDPOINT = "cam1"   # MediaMTX endpoint

# === Custom RTSP Video Track with Audio Access ===
class RTSPVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.rtsp_url = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{CAMERA_IP}:{RTSP_PORT}/{RTSP_STREAM}"
        print(f"[INFO] Connecting to RTSP stream: {self.rtsp_url}")

        self.player = MediaPlayer(
            self.rtsp_url,
            format="rtsp",
            options={
                "rtsp_transport": "udp",
                "buffer_size": "1M",
                "timeout": "5000000",
                "reorder_queue_size": "10"
            }
        )

        if not self.player or not self.player.video:
            raise RuntimeError("❌ Failed to access RTSP video stream. Check camera credentials or connectivity.")

        self.video = self.player.video
        self.audio = self.player.audio  # This may be None if audio not supported
        if self.audio:
            print("[INFO] Audio track detected and will be included.")
        else:
            print("[INFO] No audio track found on RTSP stream.")

    async def recv(self):
        try:
            frame = await self.video.recv()
            return frame
        except Exception as e:
            print(f"[ERROR] Error receiving video frame: {e}")
            return None

# === WebRTC Streaming Function ===
async def publish_stream():
    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    pc = RTCPeerConnection(configuration=config)

    # 🎥 Add video track
    stream = RTSPVideoTrack()
    pc.addTrack(stream)

    # 🔊 Add audio track if available (FYI - Comment this if you want to reduce CPU uses)
    if stream.audio:
        pc.addTrack(stream.audio)

    await pc.setLocalDescription(await pc.createOffer())

    whip_url = f"http://{SERVER_IP}:{SERVER_PORT}/{MediaMTX_ENDPOINT}/whip"
    print(f"[INFO] Sending offer to WHIP endpoint: {whip_url}")

    async with ClientSession() as session:
        async with session.post(
            whip_url,
            data=pc.localDescription.sdp,
            headers={"Content-Type": "application/sdp"}
        ) as resp:
            if resp.status != 201:
                print(f"[ERROR] Failed to initiate WHIP: HTTP {resp.status}")
                print(await resp.text())
                return

            sdp = await resp.text()
            print("[SUCCESS] WebRTC connection established with MediaMTX.")
            await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    # Keep the stream running
    try:
        await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("[INFO] Stream interrupted by user.")
    finally:
        print("[INFO] Closing WebRTC connection.")
        await pc.close()

# === Entry Point ===
async def main():
    try:
        await publish_stream()
    except Exception as e:
        print(f"[FATAL] Unhandled exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())