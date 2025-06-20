#!/bin/bash
#Date: Sun 15th Jun 2025
set -e  # Exit on any error

echo "📦 Step 1: Updating system packages..."
sudo apt update -y

echo "🎥 Step 2: Installing system dependencies for FFmpeg & RTSP support..."
sudo apt install -y \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libv4l-dev \
    python3-venv \
    python3-pip

echo "🐍 Step 3: Creating Python virtual environment: rtsp_env"
python3 -m venv rtsp_env

echo "📥 Step 4: Activating virtual environment and installing Python packages..."
source rtsp_env/bin/activate
cd rtsp_env
pip install --upgrade pip
pip install aiortc aiohttp av

echo "📝 Step 5: Saving installed packages to requirements.txt"
pip freeze > requirements.txt

echo "📄 Step 6: Writing sample RTSP WebRTC script to send_rtsp_to_mediamtx.py"
cat <<EOF > send_rtsp_to_mediamtx.py
import asyncio
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaPlayer
from aiohttp import ClientSession

class RTSPVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.rtsp_url = "rtsp://pradip:52335233@192.168.0.111:554/stream2"
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
        self.video = self.player.video

    async def recv(self):
        try:
            frame = await self.player.video.recv()
            return frame
        except Exception as e:
            print(f"Error receiving frame: {e}")
            return None

async def publish_stream():
    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    pc = RTCPeerConnection(config)

    video_track = RTSPVideoTrack()
    pc.addTrack(video_track)

    await pc.setLocalDescription(await pc.createOffer())
    async with ClientSession() as session:
        async with session.post(
            "http://your_server_ip:8889/cam1/whip",
            data=pc.localDescription.sdp,
            headers={"Content-Type": "application/sdp"}
        ) as resp:
            if resp.status != 201:
                print(f"Failed to initiate WHIP: {resp.status}")
                print(await resp.text())
                return
            sdp = await resp.text()
            print("✅ WebRTC connection established")
            await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    try:
        await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("⛔ Stream interrupted")
    finally:
        await pc.close()

async def main():
    await publish_stream()

if __name__ == "__main__":
    asyncio.run(main())
EOF

echo "🚀 Step 7: Running the RTSP to WebRTC streaming script"
python3 send_rtsp_to_mediamtx.py