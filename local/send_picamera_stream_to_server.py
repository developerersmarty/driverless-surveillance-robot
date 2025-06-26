# Import required modules for WebRTC, Pi Camera video capture, and HTTP
import os
import asyncio
import aiohttp
import av
import numpy as np
from picamera2 import Picamera2
from aiortc import (
    RTCPeerConnection,
    RTCConfiguration,
    RTCIceServer,
    RTCSessionDescription,
    VideoStreamTrack
)

# === Static Configuration ===
FRAME_WIDTH  = 640
FRAME_HEIGHT = 360
FRAME_RATE   = 30

SERVER_IP = "Your Server IP Address"  # Server IP address
SERVER_PORT = "8889"
MediaMTX_ENDPOINT = "cam1"

# === Custom Video Track for Pi Camera ===
class PiCameraVideoStreamTrack(VideoStreamTrack):
    """
    Custom video track to capture frames from Raspberry Pi Camera using picamera2.
    """
    kind = "video"

    def __init__(self):
        super().__init__()
        print("[INFO] Initializing Pi Camera...")

        self.picam2 = Picamera2()
        config = self.picam2.create_video_configuration(
            main={"size": (FRAME_WIDTH, FRAME_HEIGHT)},
            controls={"FrameRate": FRAME_RATE}
        )
        self.picam2.configure(config)
        self.picam2.start()
        print(f"[INFO] Pi Camera started at {FRAME_WIDTH}x{FRAME_HEIGHT}@{FRAME_RATE}fps")

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        # Capture frame as NumPy array
        frame = self.picam2.capture_array()

        # Convert to RGB and wrap in VideoFrame
        frame_rgb = np.ascontiguousarray(frame[..., :3])
        video_frame = av.VideoFrame.from_ndarray(frame_rgb, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame

# === WebRTC Streaming Function ===
async def publish_stream():
    print("[INFO] Preparing WebRTC connection to MediaMTX...")

    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    pc = RTCPeerConnection(configuration=config)

    # Attach video track from Pi camera
    video_track = PiCameraVideoStreamTrack()
    pc.addTrack(video_track)

    # Create SDP offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("[INFO] SDP offer created successfully")

    # Send offer to WHIP endpoint
    whip_url = f"http://{SERVER_IP}:{SERVER_PORT}/{MediaMTX_ENDPOINT}/whip"
    print(f"[INFO] Sending offer to WHIP endpoint: {whip_url}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            whip_url,
            data=pc.localDescription.sdp,
            headers={"Content-Type": "application/sdp"}
        ) as resp:
            if resp.status != 201:
                print(f"[ERROR] WHIP connection failed: HTTP {resp.status}")
                print(await resp.text())
                return

            answer_sdp = await resp.text()
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer_sdp, type="answer")
            )
            print("[SUCCESS] WebRTC connection established with MediaMTX!")

    # Keep stream alive
    try:
        await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("[INFO] Stream interrupted by user.")
    finally:
        await pc.close()
        video_track.picam2.stop()
        print("[INFO] Stream closed and Pi Camera released.")

# === Entry Point ===
if __name__ == "__main__":
    try:
        asyncio.run(publish_stream())
    except Exception as e:
        print(f"[FATAL] Unhandled exception: {e}")