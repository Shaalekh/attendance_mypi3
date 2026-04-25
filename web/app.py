import os
import re
import threading
import logging
import socket

import cv2
from flask import Flask, render_template, Response, request, jsonify

logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
_IMAGES_DIR = os.path.join(_REPO_ROOT, "ui", "card", "images")
_DB_PATH = os.path.join(_REPO_ROOT, "ui", "card", "profiles.db")

app = Flask(__name__, template_folder="templates", static_folder="static")

_camera_service = None
_captured_frame = None
_frame_lock = threading.Lock()

# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _name_to_face_id(name: str) -> str:
    """Convert a display name to a safe snake_case face_id."""
    face_id = name.lower().strip()
    face_id = re.sub(r"[^a-z0-9]+", "_", face_id)
    return face_id.strip("_")


def _generate_mjpeg():
    """Yield MJPEG frames from the shared camera service."""
    while True:
        if _camera_service is None:
            break
        frame = _camera_service.get_frame()
        if frame is None:
            continue
        # picamera2 returns RGB; imencode expects BGR
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 65])
        if not ok:
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        )


# --------------------------------------------------------------------------- #
#  Routes                                                                      #
# --------------------------------------------------------------------------- #

@app.route("/")
def index():
    return render_template("register.html")


@app.route("/video_feed")
def video_feed():
    return Response(
        _generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/capture", methods=["POST"])
def capture():
    """Freeze a frame server-side and return it as JPEG for the preview."""
    global _captured_frame
    if _camera_service is None:
        return jsonify({"success": False, "error": "Camera not available"}), 503

    frame = _camera_service.get_frame()
    if frame is None:
        return jsonify({"success": False, "error": "No frame available"}), 500

    with _frame_lock:
        _captured_frame = frame.copy()

    # Return the captured frame as a JPEG so the browser can preview it
    frame_bgr = cv2.cvtColor(_captured_frame, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", frame_bgr)
    if not ok:
        return jsonify({"success": False, "error": "Encode error"}), 500

    from flask import make_response
    resp = make_response(buf.tobytes())
    resp.headers["Content-Type"] = "image/jpeg"
    return resp


@app.route("/register", methods=["POST"])
def register():
    """Save the captured photo + profile data to disk and the SQLite database."""
    global _captured_frame

    name = request.form.get("name", "").strip()
    hindi_name = request.form.get("hindi_name", "").strip() or None

    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400

    with _frame_lock:
        if _captured_frame is None:
            return jsonify({"success": False, "error": "No photo captured yet"}), 400
        frame = _captured_frame.copy()

    face_id = _name_to_face_id(name)
    image_filename = f"{face_id}.jpg"
    image_path = os.path.join(_IMAGES_DIR, image_filename)

    # Persist image
    os.makedirs(_IMAGES_DIR, exist_ok=True)
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(image_path, frame_bgr):
        return jsonify({"success": False, "error": "Failed to save image"}), 500

    # Persist profile
    try:
        import sys
        if _REPO_ROOT not in sys.path:
            sys.path.insert(0, _REPO_ROOT)
        from ui.card.faces import ProfileDB

        with ProfileDB(_DB_PATH) as db:
            db.add_profile(face_id, name, hindi_name, image_filename)
    except Exception as exc:
        logger.error("Failed to save profile: %s", exc)
        return jsonify({"success": False, "error": "Failed to save profile"}), 500

    logger.info("Registered face_id=%s name=%s", face_id, name)
    return jsonify({"success": True, "face_id": face_id})


# --------------------------------------------------------------------------- #
#  Server startup                                                              #
# --------------------------------------------------------------------------- #

def get_local_ip() -> str:
    """Return the device's outbound IP address (best-effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_server(camera_service, port: int = 5000) -> threading.Thread:
    """Initialise the Flask app and start it in a daemon thread."""
    global _camera_service, _captured_frame
    _camera_service = camera_service
    _captured_frame = None  # reset any stale capture from a previous session

    thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        ),
        daemon=True,
        name="flask-webserver",
    )
    thread.start()
    logger.info("Flask web server started on port %d", port)
    return thread
