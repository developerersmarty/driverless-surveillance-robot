# Import necessary modules for WebRTC, RTSP media playback, and HTTP requests
import asyncio
from aiortc import (
    RTCPeerConnection,         # Core class for managing WebRTC connections
    RTCConfiguration,          # Used to define STUN/TURN server settings
    RTCIceServer,              # Defines individual STUN server entries
    RTCSessionDescription,     # Used to exchange SDP offers/answers
    VideoStreamTrack           # Base class for sending video frames
)
from aiortc.contrib.media import MediaPlayer  # Utility to play RTSP streams
from aiohttp import ClientSession             # HTTP client to make WHIP requests

# Define a custom video track class that reads frames from an RTSP stream
class RTSPVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        # 🔗 Step 1: Define your RTSP stream source (replace with your camera details)
        self.rtsp_url = "rtsp://pradip:52335233@192.168.0.111:554/stream2" #640px
        # 🎥 Step 2: Use MediaPlayer to pull video from RTSP using UDP
        # You can adjust these options to tune for latency and performance
        self.player = MediaPlayer(
            self.rtsp_url,
            format="rtsp",
            options={
                "rtsp_transport": "udp",        # Use UDP for lower latency (TCP is more stable but slower)
                "buffer_size": "1M",            # Lower buffer = faster, less delay
                "timeout": "5000000",           # 5 seconds timeout to avoid hanging
                "reorder_queue_size": "10"      # Reorder packets to avoid jitter
            }
        )
        #self.video = self.player.video  # Only capture the video stream (ignore audio)

    # This coroutine is called repeatedly to deliver each video frame
    async def recv(self):
        try:
            frame = await self.player.video.recv()
            return frame
        except Exception as e:
            print(f"Error receiving frame: {e}")
            return None

# Main function to establish a WebRTC connection and publish the RTSP stream
async def publish_stream():
    # 🌍 Step 3: Set up WebRTC connection with public STUN server to traverse NAT/firewalls
    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    pc = RTCPeerConnection(config)  # Create WebRTC PeerConnection

    # 📡 Step 4: Add the custom RTSP video track to the connection
    video_track = RTSPVideoTrack()
    pc.addTrack(video_track)

    # 🧾 Step 5: Generate a WebRTC offer (SDP) describing our stream
    await pc.setLocalDescription(await pc.createOffer())

    # 🌐 Step 6: Send SDP offer to MediaMTX using WHIP protocol (via HTTP POST)
    async with ClientSession() as session:
        async with session.post(
            "http://your_server_ip:8889/cam1/whip",         # WHIP endpoint for MediaMTX
            data=pc.localDescription.sdp,                  # Send our offer SDP
            headers={"Content-Type": "application/sdp"}    # Required content-type for WHIP
        ) as resp:
            if resp.status != 201:
                # Something went wrong — show response details
                print(f"Failed to initiate WHIP: {resp.status}")
                print(await resp.text())
                return

            # ✅ If successful, get the server’s SDP answer and complete WebRTC handshake
            sdp = await resp.text()
            print("WebRTC connection established")
            await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    # 🕒 Step 7: Keep the stream running for 1 hour (or until interrupted)
    try:
        await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("Stopping stream...")
    finally:
        # 🔚 Cleanup: Close the WebRTC connection
        await pc.close()

# 🔁 Entry point: Start the stream
async def main():
    await publish_stream()

if __name__ == "__main__":
    # Run the main coroutine
    asyncio.run(main())