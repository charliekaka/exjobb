import RPi.GPIO as GPIO
import time
import glob
import os
import subprocess
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from datetime import datetime
import paho.mqtt.client as mqtt
import json
import host

# MQTT
BROKER_IP = "10.0.32.29" # min dators broker
BROKER_PORT = 1883

TOPIC_MOTION = "home/pi/motion"
TOPIC_CLIP = "home/pi/clip"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "raspberry_pi")
client.connect(BROKER_IP, BROKER_PORT, 60)
client.loop_start()

# GPIO
LED = 4
PIR = 27

CLIP_DIR = "/home/exjobb/clips"
MAX_CLIPS = 10
RECORD_SECONDS = 15

os.makedirs(CLIP_DIR, exist_ok=True)

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED, GPIO.OUT)
GPIO.setup(PIR, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Camera
picam = Picamera2()
config = picam.create_video_configuration(
    main={"size": (1280, 720)},
    controls={"FrameRate": 10}
)
picam.configure(config)
picam.start()

# diod lyser
GPIO.output(LED, GPIO.HIGH)

#startar http server på rpi
host.start()

# skriv fil class
class MJPEGFileOutput(FileOutput):
    def __init__(self, path):
        self.file = open(path, "wb")
        self.path = path

    def outputframe(self, frame, keyframe=True, timestamp=None, packet=None, audio=None):
        self.file.write(frame)

    def stop(self):
        self.file.close()


def convert_to_mp4(mjpeg_path):
    mp4_path = mjpeg_path.replace(".mjpeg", ".mp4")
    thumb_path = mjpeg_path.replace(".mjpeg", ".jpg")

    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", "10",
        "-i", mjpeg_path,
        "-vcodec", "libx264",
        "-preset", "fast",
        "-movflags", "+faststart",
        mp4_path
    ], check=True)

    # thumbnail as first frame
    subprocess.run([
        "ffmpeg", "-y",
        "-i", mp4_path,
        "-vframes", "1",
        "-q:v", "2",
        thumb_path
    ], check=True)

    return mp4_path


def record_clip():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mjpeg_path = f"{CLIP_DIR}/{timestamp}.mjpeg"

    encoder = MJPEGEncoder(bitrate=4000000)
    output = MJPEGFileOutput(mjpeg_path)

    picam.start_recording(encoder, output)
    time.sleep(RECORD_SECONDS)
    picam.stop_recording()
    output.stop()

    mp4_path = convert_to_mp4(mjpeg_path)

    # Clean up old clips
    clips = sorted(glob.glob(f"{CLIP_DIR}/*.mp4"))
    while len(clips) > MAX_CLIPS:
        oldest = clips.pop(0)
        base = oldest.replace(".mp4", "")
        for ext in [".mp4", ".mjpeg", ".jpg"]:
            if os.path.exists(base + ext):
                os.remove(base + ext)

    # clip list
    clips = sorted(glob.glob(f"{CLIP_DIR}/*.mp4"), reverse=True)
    clip_list = [
        {
            "url": f"http://10.0.32.19:8080/clips/{os.path.basename(c)}",
            "thumb": f"http://10.0.32.19:8080/clips/{os.path.basename(c).replace('.mp4', '.jpg')}",
            "name": os.path.basename(c).replace(".mp4", "")
        }
        for c in clips
    ]

    client.publish(TOPIC_CLIP, json.dumps({"clips": clip_list}))
    url = clip_list[0]["url"]
    print("Clip ready:", url)


try:
    pir_was_low = True

    while True:
        if GPIO.input(PIR) == GPIO.HIGH:
            if pir_was_low:     # rising flank
                print("Motion detected!")
                client.publish(TOPIC_MOTION, "on")
                record_clip()       # takes 15 seconds
                client.publish(TOPIC_MOTION, "off")
                pir_was_low = False
        else:
            pir_was_low = True

        time.sleep(0.2)

finally: # always runs on exit
    GPIO.cleanup()
    client.loop_stop()
    client.disconnect()
    picam.stop()