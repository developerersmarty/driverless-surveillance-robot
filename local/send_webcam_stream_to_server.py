#send_webcam_stream_to_server.py
# Import required modules for WebRTC, video capture, and HTTP communication
import os
import cv2                            # For webcam video capture
import asyncio                        # For asynchronous event loop
import aiohttp                        # For sending HTTP (WHIP) requests
import av                             # For video frame encoding
from aiortc import (
    RTCPeerConnection,               # Core class for managing WebRTC connections
    RTCConfiguration,                # Configuration for STUN/TURN servers
    RTCIceServer,                    # STUN server entry
    RTCSessionDescription,           # WebRTC SDP offer/answer
    VideoStreamTrack                 # Base class for sending video frames
)

# === Static Configuration ===
#Please not the bellow value should be in number format nto string format
CAMERA_INDEX = 0        # Index of webcam (0 = default webcam)
FRAME_WIDTH  = 640      # Desired video width
FRAME_HEIGHT = 360      # Desired video height

SERVER_IP = "Your Server Ip"  # Your Server IP address
SERVER_PORT = "8889"         # Port for WebRTC (Make sure to enable this port & run MediaMTX on server)
MediaMTX_ENDPOINT = "cam1"   # MediaMTX endpoint

# === Define a custom video track class that reads frames from a webcam ===
class WebcamVideoStreamTrack(VideoStreamTrack):
    """
    Custom video track to capture frames from a webcam device using OpenCV.
    This class is passed to the WebRTC connection as the source of video frames.
    """
    kind = "video"

    def __init__(self):
        super().__init__()mat
        # 🔌 Step 1: Open webcam device at the given index
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            raise RuntimeError("❌ Failed to open webcam. Check if the camera is connected and available.")

        # 🎥 Step 2: Set desired resolution (optional)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

        print(f"[INFO] Webcam initialized on index {CAMERA_INDEX} at resolution {FRAME_WIDTH}x{FRAME_HEIGHT}")

    async def recv(self):
        """
        Called repeatedly by WebRTC to get the next video frame.
        Converts OpenCV frame to aiortc-compatible for.
        """
        pts, time_base = await self.next_timestamp()  # Generate timestamp for the frame
        ret, frame = self.cap.read()  # Capture frame

        if not ret:
            raise RuntimeError("❌ Failed to read frame from webcam.")

        # Convert BGR (OpenCV format) to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert NumPy array to aiortc VideoFrame
        video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        #print("[INFO] Frame captured and sent")
        return video_frame

# === Main function to establish a WebRTC connection and publish the webcam stream ===
async def publish_stream():
    print("[INFO] Preparing WebRTC connection to MediaMTX (Server)...")

    # 🌍 Step 3: Create WebRTC peer connection with a STUN server (for NAT traversal)
    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    pc = RTCPeerConnection(configuration=config)

    # 📡 Step 4: Create and attach video track from webcam
    video_track = WebcamVideoStreamTrack()
    pc.addTrack(video_track)

    # 🧾 Step 5: Generate SDP offer from the client (this device)
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("[INFO] SDP offer created successfully")

    # 🌐 Step 6: Send SDP offer to MediaMTX WHIP endpoint via HTTP POST
    whip_url = f"http://{SERVER_IP}:{SERVER_PORT}/{MediaMTX_ENDPOINT}/whip" 
    print(f"[INFO] Sending offer to WHIP endpoint: {whip_url}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            whip_url,
            data=pc.localDescription.sdp,                    # SDP offer body
            headers={"Content-Type": "application/sdp"}      # Required header for WHIP
        ) as resp:
            if resp.status != 201:
                print(f"[ERROR] WHIP connection failed: HTTP {resp.status}")
                print(await resp.text())
                return

            # ✅ Step 7: Receive SDP answer from server and complete WebRTC handshake
            answer_sdp = await resp.text()
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer_sdp, type="answer")
            )
            print("[SUCCESS] WebRTC connection established with MediaMTX!")

    # 🕒 Step 8: Keep stream alive for 1 hour or until manually stopped
    try:
        await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("[INFO] Stream interrupted by user.")
    finally:
        # 🔚 Step 9: Cleanup
        await pc.close()
        video_track.cap.release()
        print("[INFO] Stream closed and webcam released.")

# === Entry Point ===
if __name__ == "__main__":
    try:
        asyncio.run(publish_stream())
    except Exception as e:
        print(f"[FATAL] Unhandled exception: {e}")