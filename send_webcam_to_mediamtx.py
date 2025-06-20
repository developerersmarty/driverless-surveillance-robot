# send_webcam_to_mediamtx.py
import cv2
import asyncio
import aiohttp
import av
from aiortc import (
    RTCPeerConnection,
    RTCConfiguration,
    RTCIceServer,
    RTCSessionDescription,
    VideoStreamTrack,
)


# ✅ Webcam video track from your original working webcam code
class WebcamVideoStreamTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise RuntimeError("❌ Failed to open webcam")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("[INFO] Webcam initialized")

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()
        if not ret:
            raise Exception("❌ Failed to read from webcam")

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        print("[INFO] Frame sent from webcam")
        return video_frame


# ✅ WHIP publisher to MediaMTX (unchanged logic)
async def publish_stream():
    print("[INFO] Connecting to MediaMTX via WHIP...")

    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    pc = RTCPeerConnection(configuration=config)

    video_track = WebcamVideoStreamTrack()
    pc.addTrack(video_track)

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("[INFO] SDP offer created")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://your_server_ip:8889/cam1/whip",
            data=pc.localDescription.sdp,
            headers={"Content-Type": "application/sdp"},
        ) as resp:
            if resp.status != 201:
                print(f"[ERROR] WHIP offer failed: {resp.status}")
                print(await resp.text())
                return

            answer_sdp = await resp.text()
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer_sdp, type="answer")
            )
            print("[INFO] WebRTC connection established!")

    try:
        await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("[INFO] Interrupted by user")
    finally:
        await pc.close()
        video_track.cap.release()
        print("[INFO] Stream closed and camera released")


if __name__ == "__main__":
    asyncio.run(publish_stream())