import asyncio # Asyncio library for asynchronous programming
import websockets # WebSocket library for async communication
import json # JSON library for data serialization
import RPi.GPIO as GPIO # GPIO library for Raspberry Pi pin control
import time # Time library for delays
import threading  # Threading library for running sensor loop in background
from onvif import ONVIFCamera # ONVIF library for camera control

# === Static Configuration ===
SERVER_IP = "Your Server IP"  # Replace with your server's IP address
SERVER_PORT = 9000 # Port for WebSocket communication on the server
CAMERA_IP = "Your Camera IP"  # Replace with your camera's IP address
ONVIF_USER = "Your ONVIF Username"  # Replace with your ONVIF username
ONVIF_PASS = "Your ONVIF Password"  # Replace with your ONVIF password
ONVIF_PORT = 2020 # Default ONVIF port, change if needed
WSDL_DIR = '/home/pi/webcam_env/lib/python3.11/site-packages/wsdl' # Path to ONVIF WSDL files, adjust if necessary

# === GPIO Setup ===
GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

# === Motor Pins ===
l_en_r, r_en_r, l_pwm_r, r_pwm_r = 35, 36, 38, 37 # Driver 1 (Front motor)
l_en_f, r_en_f, l_pwm_f, r_pwm_f = 15, 16, 33, 13 # Driver 2 (Rear motor)
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
TRIG = 31 # Trigger pin for ultrasonic sensor
ECHO = 32 # Echo pin for ultrasonic sensor
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
latest_distance = -1 # Initialize latest_distance to -1 to indicate no reading ye
AUTO_BRAKE = True # Enable automatic braking if an obstacle is detected

# === ONVIF Setup ===
try:
    print(f"Connecting to ONVIF Camera at {CAMERA_IP}:{ONVIF_PORT}...")
    cam = ONVIFCamera(CAMERA_IP, ONVIF_PORT, ONVIF_USER, ONVIF_PASS, wsdl_dir=WSDL_DIR)
    media_service = cam.create_media_service()
    ptz_service = cam.create_ptz_service()
    profile = media_service.GetProfiles()[0]
    ptz_token = profile.token
    print(f"Connected to camera. Profile: {profile.Name}")
except Exception as e:
    print(f"ONVIF setup failed: {type(e).__name__}: {e}")
    ptz_service = None
    ptz_token = None

# === Motor Control ===
def stop_all():
    for p in pwms.values():
        p.ChangeDutyCycle(0)

def handle_drive_action(action, speed):
    global latest_distance # Use global variable to access latest_distanc
    stop_all() # Stop all motors before executing new actio
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

# === Camera PT Movement ===
def handle_camera_movement(direction):
    if not ptz_service or not ptz_token:
        print("ONVIF not configured")
        return
    try:
        velocity = {'PanTilt': {'x': 0.0, 'y': 0.0}, 'Zoom': 0.0} # Initialize velocity for PanTilt and Zoo
        if direction == "cam_left":
            velocity['PanTilt']['x'] = -0.5
        elif direction == "cam_right":
            velocity['PanTilt']['x'] = 0.5
        elif direction == "cam_up":
            velocity['PanTilt']['y'] = 0.5
        elif direction == "cam_down":
            velocity['PanTilt']['y'] = -0.5
        else:
            print(f"Unknown camera direction: {direction}")
            return

        ptz_service.ContinuousMove({
            'ProfileToken': ptz_token,
            'Velocity': velocity,
            'Timeout': 'PT1S'
        })
        time.sleep(0.5)
        ptz_service.Stop({'ProfileToken': ptz_token})
    except Exception as e:
        print(f"Camera movement failed: {type(e).__name__}: {e}")


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
    distance = round(duration * 17150, 2) # Convert time to distance in c
    return distance if 2 <= distance <= 300 else -1

def sensor_loop(): # Continuously read distance sensor in a separate thread
    global latest_distance
    while True:
        dist = read_distance() # Read distance from the sensor
        latest_distance = dist # Update the latest distance readin
        time.sleep(0.5) # Sleep for 0.5 seconds before next reading

# === WebSocket: Send distance to /control ===
async def websocket_handler():
    uri = f"ws://{SERVER_IP}:9000/control" # WebSocket URI for distance messages
    async with websockets.connect(uri) as websocket:
        print("WebSocket connected to /control")
        threading.Thread(target=sensor_loop, daemon=True).start()

        async def send_distance():
            while True:
                if latest_distance != -1:
                    await websocket.send(json.dumps({"type": "distance", "value": latest_distance}))
                await asyncio.sleep(0.5)
        asyncio.create_task(send_distance())

        # Listen for messages from server (if any)
        async for message in websocket:
            print(f"Unexpected /control message: {message}")

# === WebSocket: Receive commands from /pi_control ===
async def pi_control_handler(): 
    uri = f"ws://{SERVER_IP}:9000/pi_control" # WebSocket URI for camera/robot control
    async with websockets.connect(uri) as websocket:
        print("WebSocket connected to /pi_control")
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get("action")
                value = data.get("value", 100)
                print(f"Received from browser: {data}")
                if action in ["forward", "backward", "left", "right", "stop"]:
                    handle_drive_action(action, value)
                elif action in ["cam_left", "cam_right", "cam_up", "cam_down"]:
                    handle_camera_movement(action)
                else:
                    print(f"Unknown action: {action}")
            except Exception as e:
                print(f"Error handling message: {e}")

# === Main Async Runner ===
async def main():
    await asyncio.gather(
        websocket_handler(), # Start WebSocket handler for distance sensor
        pi_control_handler() # Start WebSocket handler for camera/robot control
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        print("Cleanup")
        stop_all()
        for p in pwms.values():
            p.stop()
        GPIO.cleanup()
