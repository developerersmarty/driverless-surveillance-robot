import asyncio
import websockets
import json
import RPi.GPIO as GPIO
import time
import threading
from zeep import Client
from dotenv import load_dotenv
import os

# === Load environment variables ===
load_dotenv()

SERVER_IP = os.getenv("Server_IP")
CAMERA_IP = os.getenv("Camera_IP")
ONVIF_USER = os.getenv("ONVIF_USER")
ONVIF_PASS = os.getenv("ONVIF_PASS")
ONVIF_URL = os.getenv("ONVIF_URL")

# === GPIO Setup ===
GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

# === Motor Pins ===
l_en_r, r_en_r, l_pwm_r, r_pwm_r = 35, 36, 38, 37  # Reverse
l_en_f, r_en_f, l_pwm_f, r_pwm_f = 15, 16, 33, 13  # Forward
motor_pins = [l_en_r, r_en_r, l_pwm_r, r_pwm_r, l_en_f, r_en_f, l_pwm_f, r_pwm_f]
for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)
for pin in [l_en_r, r_en_r, l_en_f, r_en_f]:
    GPIO.output(pin, True)

pwms = {
    'l_r': GPIO.PWM(l_pwm_r, 100),
    'r_r': GPIO.PWM(r_pwm_r, 100),
    'l_f': GPIO.PWM(l_pwm_f, 100),
    'r_f': GPIO.PWM(r_pwm_f, 100),
}
for p in pwms.values():
    p.start(0)

# === Distance Sensor ===
TRIG = 31
ECHO = 32
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
latest_distance = -1
AUTO_BRAKE = True

# === ONVIF Setup ===
try:
    ptz_client = Client(ONVIF_URL)
    ptz_service = ptz_client.create_service(
        "{http://www.onvif.org/ver20/ptz/wsdl}PTZ",
        ONVIF_URL.replace("device_service", "ptz_service")
    )
    media_client = Client(ONVIF_URL)
    media_service = media_client.create_service(
        "{http://www.onvif.org/ver10/media/wsdl}Media",
        ONVIF_URL.replace("device_service", "media_service")
    )
    profile = media_service.GetProfiles()[0]
    ptz_config = ptz_service.GetConfigurations()[0]
except Exception as e:
    print(f"ONVIF setup failed: {e}")
    ptz_service = None
    profile = None

# === Motor Control ===
def stop_all():
    for p in pwms.values():
        p.ChangeDutyCycle(0)

def handle_drive_action(action, speed):
    global latest_distance
    stop_all()
    if action == "forward" and AUTO_BRAKE and latest_distance != -1 and latest_distance < 25:
        print("Emergency brake: Obstacle too close")
        return
    if action == "forward":
        pwms['r_r'].ChangeDutyCycle(speed)
    elif action == "backward":
        pwms['l_r'].ChangeDutyCycle(speed)
    elif action == "left":
        pwms['r_f'].ChangeDutyCycle(speed)
    elif action == "right":
        pwms['l_f'].ChangeDutyCycle(speed)
    elif action == "stop":
        stop_all()

# === ONVIF Camera Control ===
def handle_camera_movement(direction):
    if not ptz_service or not profile:
        print("ONVIF not configured")
        return
    try:
        velocity = {'PanTilt': {'x': 0, 'y': 0}, 'Zoom': 0}
        if direction == "cam_left":
            velocity['PanTilt']['x'] = -0.5
        elif direction == "cam_right":
            velocity['PanTilt']['x'] = 0.5
        elif direction == "cam_up":
            velocity['PanTilt']['y'] = 0.5
        elif direction == "cam_down":
            velocity['PanTilt']['y'] = -0.5
        ptz_service.ContinuousMove({
            'ProfileToken': profile.token,
            'Velocity': velocity,
            'Timeout': 'PT1S'
        })
        time.sleep(0.5)
        ptz_service.Stop({'ProfileToken': profile.token})
    except Exception as e:
        print(f"Camera movement failed: {e}")

def handle_camera_zoom(level):
    if not ptz_service or not profile:
        print("ONVIF not configured")
        return
    try:
        velocity = {'PanTilt': {'x': 0, 'y': 0}, 'Zoom': level / 100}
        ptz_service.ContinuousMove({
            'ProfileToken': profile.token,
            'Velocity': velocity,
            'Timeout': 'PT1S'
        })
        time.sleep(0.5)
        ptz_service.Stop({'ProfileToken': profile.token})
    except Exception as e:
        print(f"Camera zoom failed: {e}")

# === Distance Sensor Reading ===
def read_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)
    start = time.time()
    timeout = start + 0.05
    while GPIO.input(ECHO) == 0 and time.time() < timeout:
        start = time.time()
    stop = time.time()
    timeout = stop + 0.05
    while GPIO.input(ECHO) == 1 and time.time() < timeout:
        stop = time.time()
    duration = stop - start
    distance = round(duration * 17150, 2)
    return distance if 2 <= distance <= 300 else -1

def sensor_loop():
    global latest_distance
    while True:
        dist = read_distance()
        latest_distance = dist
        time.sleep(0.5)

# === WebSocket Handler ===
async def websocket_handler():
    uri = f"ws://{SERVER_IP}:9000/control"
    async with websockets.connect(uri) as websocket:
        print("WebSocket connected to server")
        threading.Thread(target=sensor_loop, daemon=True).start()

        async def send_distance():
            while True:
                if latest_distance != -1:
                    await websocket.send(json.dumps({"type": "distance", "value": latest_distance}))
                await asyncio.sleep(0.5)
        asyncio.create_task(send_distance())

        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get("action")
                value = data.get("value", 100)
                print(f"Received: {data}")
                if action in ["forward", "backward", "left", "right", "stop"]:
                    handle_drive_action(action, value)
                elif action in ["cam_left", "cam_right", "cam_up", "cam_down"]:
                    handle_camera_movement(action)
                elif action == "zoom":
                    handle_camera_zoom(value)
            except json.JSONDecodeError:
                print(f"Invalid JSON: {message}")

async def main():
    while True:
        try:
            await websocket_handler()
        except (websockets.exceptions.ConnectionClosed, Exception) as e:
            print(f"WebSocket error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        print("Cleanup")
        stop_all()
        for p in pwms.values():
            p.stop()
        GPIO.cleanup()