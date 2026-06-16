import os
import re
import threading
import logging
import socket
from datetime import datetime, timezone

import cv2
import numpy as np
from flask import Flask, render_template, request, jsonify

from services.aws_service import AWSService

logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
_IMAGES_DIR = os.path.join(_REPO_ROOT, "ui", "card", "images")
_DB_PATH = os.path.join(_REPO_ROOT, "ui", "card", "profiles.db")

app = Flask(__name__, template_folder="templates", static_folder="static")

_camera_service = None


def _normalize_face_id(face_id: str) -> str:
    cleaned = face_id.lower().strip()
    cleaned = re.sub(r"[^a-z0-9_]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


@app.route("/")
def index():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    hindi_name = request.form.get("hindi_name", "").strip() or None
    face_id_input = request.form.get("face_id", "").strip()
    photo = request.files.get("photo")

    if not face_id_input:
        return jsonify({"success": False, "error": "face_id is required"}), 400
    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400
    if photo is None or not photo.filename:
        return jsonify({"success": False, "error": "Photo is required"}), 400

    face_id = _normalize_face_id(face_id_input)
    if not face_id:
        return jsonify({"success": False, "error": "Invalid face_id"}), 400
    if face_id != face_id_input.lower().strip():
        return jsonify(
            {
                "success": False,
                "error": "face_id may only contain lowercase letters, numbers, and underscores",
            }
        ), 400

    image_bytes = photo.read()
    if not image_bytes:
        return jsonify({"success": False, "error": "Uploaded photo is empty"}), 400

    frame_bgr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame_bgr is None:
        return jsonify({"success": False, "error": "Invalid image upload"}), 400

    image_filename = f"{face_id}.jpg"
    image_path = os.path.join(_IMAGES_DIR, image_filename)
    registered_at = datetime.now(timezone.utc).isoformat()
    aws = AWSService()

    try:
        import sys
        if _REPO_ROOT not in sys.path:
            sys.path.insert(0, _REPO_ROOT)
        from ui.card.faces import ProfileDB

        with ProfileDB(_DB_PATH) as db:
            existing = db.get_profile(face_id)
            if existing is not None:
                return jsonify(
                    {
                        "success": False,
                        "error": f"face_id '{face_id}' already exists. Use a different face_id.",
                    }
                ), 409

            if aws.face_id_exists(face_id):
                return jsonify(
                    {
                        "success": False,
                        "error": f"face_id '{face_id}' already exists in Rekognition. Use a different face_id.",
                    }
                ), 409

            aws.index_face_bytes(image_bytes, face_id)

            os.makedirs(_IMAGES_DIR, exist_ok=True)
            if not cv2.imwrite(image_path, frame_bgr):
                return jsonify({"success": False, "error": "Failed to save image"}), 500

            db.add_profile(
                face_id=face_id,
                name=name,
                hindi_name=hindi_name,
                image_url=image_filename,
                registered_at=registered_at,
            )
    except Exception as exc:
        logger.exception("Failed to register face_id=%s", face_id)
        return jsonify({"success": False, "error": f"Registration failed: {exc}"}), 500

    logger.info("Registered face_id=%s name=%s", face_id, name)
    return jsonify(
        {
            "success": True,
            "face_id": face_id,
            "collection_id": aws.collection_id,
            "registered_at": registered_at,
        }
    )


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
    global _camera_service
    _camera_service = camera_service

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
