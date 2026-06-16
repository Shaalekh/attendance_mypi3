import subprocess
import tkinter as tk
from PIL import Image, ImageTk
import cv2
import time
import os
import re
from collections import OrderedDict
from datetime import datetime
import threading
import logging

from services.camera_service import CameraService
from services.face_service import FaceService
from services.aws_service import AWSService
from services.gpio_service import GPIOService
from ui.card.faces import ProfileDB

logger = logging.getLogger(__name__)


class MainWindow:
    # GPIO BCM pin number for the latching config switch
    _CONFIG_SWITCH_PIN = 26
    # Flask web-server port
    _WEB_PORT = 5000
    # Switch must remain OFF this long before reboot is triggered
    _REBOOT_HOLD_SECONDS = 2
    _PROFILE_DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ui",
        "card",
        "profiles.db",
    )
    _PROFILE_IMAGES_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ui",
        "card",
        "images",
    )
    _PROFILE_IMAGE_SIZE = (480, 320)
    _PROFILE_ROW_CACHE_LIMIT = 128
    _PROFILE_IMAGE_CACHE_LIMIT = 64
    _PROFILE_CARD_VISIBLE_MS = 2000

    def __init__(self):
        self.root = tk.Tk()

        # Fixed window (no borders)
        self.root.overrideredirect(True)
        self.root.geometry("480x320")

        # ESC to exit (dev only)
        self.root.bind("<Escape>", lambda e: self.close())

        self.camera = None
        self.face_service = FaceService()
        self.aws_service = AWSService()
        self._camera_error: str | None = None

        self.last_check = 0
        self._processing_event = threading.Event()
        self.frame_count = 0

        # Config-mode state
        self._config_mode = False
        self._config_frame: tk.Frame | None = None
        self._ip_label: tk.Label | None = None
        self._mode_label: tk.Label | None = None
        self._web_thread: threading.Thread | None = None
        self._gpio_service: GPIOService | None = None
        self._switch_is_on = False
        self._reboot_armed = False
        self._reboot_after_id: str | None = None
        self._rebooting = False
        self._profile_overlay_frame: tk.Frame | None = None
        self._profile_image_label: tk.Label | None = None
        self._profile_name_label: tk.Label | None = None
        self._profile_datetime_label: tk.Label | None = None
        self._profile_secondary_label: tk.Label | None = None
        self._profile_image_ref: ImageTk.PhotoImage | None = None
        self._profile_hide_after_id: str | None = None
        self._profile_row_cache: OrderedDict[str, dict | None] = OrderedDict()
        self._profile_image_cache: OrderedDict[str, Image.Image | None] = OrderedDict()
        self._cache_lock = threading.Lock()

        self.create_widgets()
        self._initialise_camera()
        self._setup_gpio()
        self.update_camera()

    def create_widgets(self):
        self.camera_label = tk.Label(self.root)
        self.camera_label.pack(fill="both", expand=True)

        self.status_label = tk.Label(
            self.root,
            text="Ready",
            font=("Arial", 20),
            fg="white",
            bg="black"
        )
        self.status_label.place(x=20, y=20)
        self._create_profile_overlay()

    def _create_profile_overlay(self) -> None:
        """Create a reusable full-screen profile card overlay (hidden by default)."""
        self._profile_overlay_frame = tk.Frame(self.root, bg="black")

        card_frame = tk.Frame(
            self._profile_overlay_frame,
            bg="#121212",
            highlightthickness=2,
            highlightbackground="#2b2b2b",
        )
        card_frame.place(relx=0.5, rely=0.5, anchor="center")

        self._profile_image_label = tk.Label(
            card_frame,
            text="No image",
            font=("Arial", 16),
            fg="#9e9e9e",
            bg="#1e1e1e",
            width=28,
            height=10,
        )
        self._profile_image_label.pack(padx=40, pady=(34, 24))

        self._profile_name_label = tk.Label(
            card_frame,
            text="",
            font=("Arial", 36, "bold"),
            fg="white",
            bg="#121212",
        )
        self._profile_name_label.pack(pady=(0, 12))

        self._profile_datetime_label = tk.Label(
            card_frame,
            text="",
            font=("Arial", 18),
            fg="#d0d0d0",
            bg="#121212",
        )
        self._profile_datetime_label.pack(pady=(0, 8))

        self._profile_secondary_label = tk.Label(
            card_frame,
            text="",
            font=("Arial", 14),
            fg="#9e9e9e",
            bg="#121212",
        )
        self._profile_secondary_label.pack(pady=(0, 30))

    def show_profile_card(
        self,
        name: str,
        datetime_text: str,
        image_pil: Image.Image | None = None,
        image_path: str | None = None,
        secondary_text: str | None = None,
    ) -> None:
        """Show the profile card overlay with payload data."""
        if self._config_mode or not self._profile_overlay_frame:
            return

        self._profile_name_label.config(text=name or "")
        self._profile_datetime_label.config(text=datetime_text or "")
        self._profile_secondary_label.config(text=secondary_text or "")

        if self._profile_image_label is None:
            return

        self._profile_image_ref = None
        if image_pil is not None:
            self._profile_image_ref = ImageTk.PhotoImage(image_pil)
            self._profile_image_label.config(
                image=self._profile_image_ref,
                text="",
                width=self._PROFILE_IMAGE_SIZE[0],
                height=self._PROFILE_IMAGE_SIZE[1],
            )
        elif image_path:
            try:
                img = Image.open(image_path)
                img = img.resize(self._PROFILE_IMAGE_SIZE, Image.LANCZOS)
                self._profile_image_ref = ImageTk.PhotoImage(img)
                self._profile_image_label.config(
                    image=self._profile_image_ref,
                    text="",
                    width=self._PROFILE_IMAGE_SIZE[0],
                    height=self._PROFILE_IMAGE_SIZE[1],
                )
            except Exception:
                logger.exception("Failed to load profile overlay image: %s", image_path)
                self._profile_image_label.config(
                    image="",
                    text="Image unavailable",
                    width=28,
                    height=10,
                )
        else:
            self._profile_image_label.config(
                image="",
                text="No image",
                width=28,
                height=10,
            )

        if self._profile_hide_after_id:
            self.root.after_cancel(self._profile_hide_after_id)
            self._profile_hide_after_id = None

        self._profile_overlay_frame.place(x=0, y=0, relwidth=1, relheight=1)
        self._profile_overlay_frame.lift()
        self._schedule_profile_card_hide()

    def hide_profile_card(self) -> None:
        """Hide the profile card overlay."""
        if self._profile_hide_after_id:
            self.root.after_cancel(self._profile_hide_after_id)
            self._profile_hide_after_id = None
        if self._profile_overlay_frame:
            self._profile_overlay_frame.place_forget()

    def _schedule_profile_card_hide(self) -> None:
        if self._profile_hide_after_id:
            self.root.after_cancel(self._profile_hide_after_id)
        self._profile_hide_after_id = self.root.after(
            self._PROFILE_CARD_VISIBLE_MS,
            self.hide_profile_card,
        )

    def _put_lru(
        self,
        cache: OrderedDict[str, dict | Image.Image | None],
        key: str,
        value: dict | Image.Image | None,
        limit: int,
    ) -> None:
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    def _get_profile_row(self, face_id: str) -> dict | None:
        with self._cache_lock:
            cached = self._profile_row_cache.get(face_id)
            if face_id in self._profile_row_cache:
                self._profile_row_cache.move_to_end(face_id)
                return cached

        try:
            with ProfileDB(self._PROFILE_DB_PATH) as db:
                row = db.get_profile(face_id)
        except Exception:
            logger.exception("Failed to fetch profile row for face_id=%s", face_id)
            return None

        profile = (
            {
                "name": row["name"],
                "hindi_name": row["hindi_name"],
                "image_url": row["image_url"],
            }
            if row is not None
            else None
        )
        with self._cache_lock:
            self._put_lru(
                self._profile_row_cache,
                face_id,
                profile,
                self._PROFILE_ROW_CACHE_LIMIT,
            )
        return profile

    def _get_profile_image(self, image_url: str | None) -> Image.Image | None:
        if not image_url:
            return None
        image_path = os.path.join(self._PROFILE_IMAGES_DIR, os.path.basename(image_url))

        with self._cache_lock:
            cached = self._profile_image_cache.get(image_path)
            if image_path in self._profile_image_cache:
                self._profile_image_cache.move_to_end(image_path)
                return cached

        if not os.path.isfile(image_path):
            logger.warning("Profile image not found: %s", image_path)
            with self._cache_lock:
                self._put_lru(
                    self._profile_image_cache,
                    image_path,
                    None,
                    self._PROFILE_IMAGE_CACHE_LIMIT,
                )
            return None

        try:
            with Image.open(image_path) as img:
                prepared = img.convert("RGB").resize(self._PROFILE_IMAGE_SIZE, Image.LANCZOS)
        except Exception:
            logger.exception("Failed to prepare profile image: %s", image_path)
            return None

        with self._cache_lock:
            self._put_lru(
                self._profile_image_cache,
                image_path,
                prepared,
                self._PROFILE_IMAGE_CACHE_LIMIT,
            )
        return prepared

    def _format_english_name(self, face_id: str, profile_name: str | None) -> str:
        if profile_name and profile_name.strip():
            return profile_name.strip()
        tokens = [
            token for token in re.split(r"[_\-\s]+", face_id.strip()) if token
        ]
        if tokens:
            return " ".join(token.capitalize() for token in tokens)
        return "Recognized"

    def _build_overlay_payload(
        self, face_id: str, timestamp: str
    ) -> tuple[str, str, str, Image.Image | None]:
        profile = self._get_profile_row(face_id)
        if profile is None:
            return self._format_english_name(face_id, None), timestamp, "Attendance marked", None

        display_name = self._format_english_name(face_id, profile["name"])
        hindi_name = profile["hindi_name"] or "Attendance marked"
        image_pil = self._get_profile_image(profile["image_url"])
        return display_name, timestamp, hindi_name, image_pil

    def _start_processing(self) -> bool:
        if self._processing_event.is_set():
            return False
        self._processing_event.set()
        return True

    def _finish_processing(self) -> None:
        self._processing_event.clear()

    def _initialise_camera(self) -> None:
        try:
            self.camera = CameraService()
            self.status_label.config(text="Ready", fg="white")
        except Exception as exc:
            self.camera = None
            self._camera_error = str(exc)
            logger.exception("Camera startup failed")
            self.status_label.config(
                text=f"Camera Error: {self._camera_error}",
                fg="orange",
            )

    def update_camera(self):
        # Don't run the attendance loop while in config mode
        if self._config_mode:
            self.root.after(200, self.update_camera)
            return

        if self.camera is None:
            self.root.after(500, self.update_camera)
            return

        try:
            frame = self.camera.get_frame()
        except Exception as exc:
            logger.exception("Camera frame capture failed")
            self.status_label.config(text=f"Camera Frame Error: {exc}", fg="orange")
            self.root.after(500, self.update_camera)
            return

        if frame is not None:

            self.frame_count += 1

            # Run detection every 3rd frame
            if self.frame_count % 3 == 0:

                small_frame = cv2.resize(frame, (320, 240))
                faces = self.face_service.detect_face(small_frame)

                for (x, y, w, h) in faces:

                    # Scale back to original size
                    scale_x = frame.shape[1] / 320
                    scale_y = frame.shape[0] / 240

                    x = int(x * scale_x)
                    y = int(y * scale_y)
                    w = int(w * scale_x)
                    h = int(h * scale_y)

                    # Trigger only if face large enough
                    if w > 120 and not self._processing_event.is_set():

                        if time.time() - self.last_check > 3:
                            if self._start_processing():
                                self.last_check = time.time()

                                face_crop = frame[y:y+h, x:x+w]

                                threading.Thread(
                                    target=self.aws_thread,
                                    args=(face_crop.copy(),),
                                    daemon=True
                                ).start()

            # Display frame
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)

            self.camera_label.imgtk = imgtk
            self.camera_label.configure(image=imgtk)
        elif not self._processing_event.is_set():
            self.status_label.config(text="Waiting for camera frame...", fg="yellow")

        self.root.after(30, self.update_camera)

    def aws_thread(self, frame):
        try:
            name = self.aws_service.recognize_face(frame)

            if name:
                timestamp = datetime.now().strftime("%d %b %Y • %I:%M %p")
                display_name, display_timestamp, secondary_text, image_pil = (
                    self._build_overlay_payload(name, timestamp)
                )
                self.root.after(
                    0,
                    lambda: self._show_recognition_overlay_from_payload(
                        display_name,
                        display_timestamp,
                        secondary_text,
                        image_pil,
                    ),
                )
            else:
                self.root.after(0, lambda: self.status_label.config(text="Unknown", fg="red"))
                self.root.after(0, self.hide_profile_card)
        except Exception as e:
            self.root.after(0, lambda: self.status_label.config(text="AWS Error", fg="orange"))
            print(e)
        finally:
            self._finish_processing()

    def _show_recognition_overlay_from_payload(
        self,
        name: str,
        timestamp: str,
        secondary_text: str,
        image_pil: Image.Image | None,
    ) -> None:
        self.show_profile_card(
            name=name,
            datetime_text=timestamp,
            image_pil=image_pil,
            secondary_text=secondary_text,
        )

    def close(self):
        if self._profile_hide_after_id:
            self.root.after_cancel(self._profile_hide_after_id)
            self._profile_hide_after_id = None
        if self._reboot_after_id:
            self.root.after_cancel(self._reboot_after_id)
            self._reboot_after_id = None
        if self._gpio_service:
            self._gpio_service.stop()
        if self.camera:
            self.camera.release()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

    # -- GPIO / config-mode ---------------------------------------------------

    def _setup_gpio(self) -> None:
        """Start monitoring the latching switch in a background thread."""
        self._gpio_service = GPIOService(
            pin=self._CONFIG_SWITCH_PIN,
            pull_up=True,
            active_low=True,
            callback_on=lambda: self.root.after(0, self._on_switch_on),
            callback_off=lambda: self.root.after(0, self._on_switch_off),
        )
        self._gpio_service.start()

    def _on_switch_on(self) -> None:
        self._switch_is_on = True
        if self._reboot_after_id:
            self.root.after_cancel(self._reboot_after_id)
            self._reboot_after_id = None
        self._enter_config_mode()
        if self._config_mode:
            self._reboot_armed = True
            if self._mode_label:
                self._mode_label.config(text="Switch ON detected. Reboot armed.", fg="#00e676")

    def _enter_config_mode(self) -> None:
        """Switch the display to config mode and start the Flask web server."""
        if self._config_mode:
            return
        self._config_mode = True

        # Build full-screen overlay on top of everything
        self._config_frame = tk.Frame(self.root, bg="black")
        self._config_frame.place(x=0, y=0, relwidth=1, relheight=1)

        # Center the config content horizontally with a fixed top offset.
        content_frame = tk.Frame(self._config_frame, bg="black")
        content_frame.place(relx=0.5, y=0, anchor="n")

        # --- WiFi / network icon (canvas arcs) ---
        icon_canvas = tk.Canvas(
            content_frame,
            bg="black",
            width=200,
            height=180,
            highlightthickness=0,
        )
        icon_canvas.pack(pady=(0, 0))

        cx, cy = 100, 155  # anchor point of the WiFi symbol (foot / dot)
        icon_canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="white", outline="white")
        for r in (28, 52, 76):
            icon_canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=45, extent=90,
                style="arc", outline="white", width=5,
            )

        # --- Labels ---
        tk.Label(
            content_frame,
            text="Web Server Mode",
            font=("Arial", 26, "bold"),
            fg="white",
            bg="black",
        ).pack(pady=(10, 2))

        tk.Label(
            content_frame,
            text="Open this address in your browser",
            font=("Arial", 16),
            fg="#aaaaaa",
            bg="black",
        ).pack()

        self._mode_label = tk.Label(
            content_frame,
            text="Starting server...",
            font=("Arial", 14, "bold"),
            fg="#fdd835",
            bg="black",
        )
        self._mode_label.pack(pady=(12, 0))

        self._ip_label = tk.Label(
            content_frame,
            text="Detecting IP…",
            font=("Arial", 16),
            fg="#00e676",
            bg="black",
        )
        self._ip_label.pack(pady=(6, 0))

        tk.Label(
            content_frame,
            text=f"Turn the switch OFF and hold for {self._REBOOT_HOLD_SECONDS} seconds to reboot",
            font=("Arial", 12, "italic"),
            fg="#555555",
            bg="black",
        ).pack(pady=(28, 0))

        # Start the Flask server (daemon thread) and update the IP label
        from web.app import start_server, get_local_ip
        try:
            self._web_thread = start_server(self.camera, port=self._WEB_PORT)
            ip = get_local_ip()
            self._ip_label.config(text=f"http://{ip}:{self._WEB_PORT}")
            if self._mode_label:
                self._mode_label.config(text="Server running", fg="#00e676")
        except Exception as exc:
            logger.exception("Failed to start config web server")
            self._ip_label.config(text="Server start failed")
            if self._mode_label:
                self._mode_label.config(text=str(exc), fg="#ff6e40")

    def _on_switch_off(self) -> None:
        """Reboot the device when the latching switch remains OFF."""
        self._switch_is_on = False
        if self._rebooting:
            return
        if not self._reboot_armed:
            if self._mode_label:
                self._mode_label.config(
                    text="Switch OFF ignored (reboot not armed)",
                    fg="#aaaaaa",
                )
            return
        if self._mode_label:
            self._mode_label.config(
                text=f"Switch OFF detected. Rebooting in {self._REBOOT_HOLD_SECONDS}s...",
                fg="#fdd835",
            )
        if self._reboot_after_id:
            self.root.after_cancel(self._reboot_after_id)
        self._reboot_after_id = self.root.after(
            self._REBOOT_HOLD_SECONDS * 1000,
            self._reboot_if_switch_stays_off,
        )

    def _reboot_if_switch_stays_off(self) -> None:
        self._reboot_after_id = None
        if self._switch_is_on or self._rebooting or not self._reboot_armed:
            return
        self._rebooting = True
        self._reboot_armed = False
        if self._mode_label:
            self._mode_label.config(text="Rebooting now...", fg="#ff6e40")
        subprocess.run(["sudo", "reboot"], check=False)
