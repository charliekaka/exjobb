from flask import Flask, send_from_directory
import os
import threading

app = Flask(__name__)

CLIP_DIR = "/home/exjobb/clips"

@app.route("/clips/<filename>")
def clips(filename):
    return send_from_directory(CLIP_DIR, filename)


def start():
    thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=8080,
            debug=False,
            use_reloader=False
        ),
        daemon=True
    )
    thread.start()
    print("HTTP server running on 8080")