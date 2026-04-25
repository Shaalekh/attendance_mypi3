import subprocess
import tkinter as tk
from PIL import Image, ImageTk
import cv2
import time
import threading

from services.camera_service import CameraService
from services.face_service import FaceService
from services.aws_service import AWSService
from services.gpio_service import GPIOService


class MainWindow:
    # GPIO BCM pin number for the latching config switch
    _CONFIG_SWITCH_PIN = 17
    # Flask web-server port
    _WEB_PORT = 5000

    def __init__(self):
        self.root = tk.Tk()

        # True fullscreen (no borders)
        self.root.overrideredirect(True)
        self.root.geometry(
            f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0"
        )

        # ESC to exit (dev only)
        self.root.bind("<Escape>", lambda e: self.close())

        self.camera = CameraService()
        self.face_service = FaceService()
        self.aws_service = AWSService()

        self.last_check = 0
        self.processing = False
        self.frame_count = 0

        # Config-mode state
        self._config_mode = False
        self._config_frame: tk.Frame | None = None
        self._ip_label: tk.Label | None = None
        self._web_thread: threading.Thread | None = None

        self.create_widgets()
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

    def update_camera(self):
        # Don't run the attendance loop while in config mode
        if self._config_mode:
            return

        frame = self.camera.get_frame()

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
                    if w > 120 and not self.processing:

                        if time.time() - self.last_check > 3:
                            self.processing = True
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

        self.root.after(30, self.update_camera)

    def aws_thread(self, frame):
        try:
            name = self.aws_service.recognize_face(frame)

            if name:
                self.status_label.config(
                    text=f"Recognized: {name}",
                    fg="green"
                )
            else:
                self.status_label.config(
                    text="Unknown",
                    fg="red"
                )
        except Exception as e:
            self.status_label.config(
                text="AWS Error",
                fg="orange"
            )
            print(e)

        self.processing = False

    def close(self):
        if self._gpio_service:
            self._gpio_service.stop()
        self.camera.release()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

    # -- GPIO / config-mode ---------------------------------------------------

    def _setup_gpio(self) -> None:
        """Start monitoring the latching switch in a background thread."""
        self._gpio_service = GPIOService(
            pin=self._CONFIG_SWITCH_PIN,
            callback_on=lambda: self.root.after(0, self._enter_config_mode),
            callback_off=lambda: self.root.after(0, self._on_switch_off),
        )
        self._gpio_service.start()

    def _enter_config_mode(self) -> None:
        """Switch the display to config mode and start the Flask web server."""
        if self._config_mode:
            return
        self._config_mode = True

        # Build full-screen overlay on top of everything
        self._config_frame = tk.Frame(self.root, bg="black")
        self._config_frame.place(x=0, y=0, relwidth=1, relheight=1)

        # --- WiFi / network icon (canvas arcs) ---
        icon_canvas = tk.Canvas(
            self._config_frame,
            bg="black",
            width=200,
            height=180,
            highlightthickness=0,
        )
        icon_canvas.pack(pady=(50, 0))

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
            self._config_frame,
            text="Configuration Mode",
            font=("Arial", 26, "bold"),
            fg="white",
            bg="black",
        ).pack(pady=(10, 4))

        tk.Label(
            self._config_frame,
            text="Open this address in your browser:",
            font=("Arial", 14),
            fg="#aaaaaa",
            bg="black",
        ).pack()

        self._ip_label = tk.Label(
            self._config_frame,
            text="Detecting IP…",
            font=("Arial", 22, "bold"),
            fg="#00e676",
            bg="black",
        )
        self._ip_label.pack(pady=(6, 0))

        tk.Label(
            self._config_frame,
            text="Turn the switch off to reboot",
            font=("Arial", 11, "italic"),
            fg="#555555",
            bg="black",
        ).pack(pady=(28, 0))

        # Start the Flask server (daemon thread) and update the IP label
        from web.app import start_server, get_local_ip
        self._web_thread = start_server(self.camera, port=self._WEB_PORT)
        ip = get_local_ip()
        self._ip_label.config(text=f"http://{ip}:{self._WEB_PORT}")

    def _on_switch_off(self) -> None:
        """Reboot the device when the latching switch is released."""
        subprocess.run(["sudo", "reboot"], check=False)
