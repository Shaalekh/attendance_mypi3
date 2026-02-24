import tkinter as tk
from PIL import Image, ImageTk
import cv2
import time
import threading

from services.camera_service import CameraService
from services.face_service import FaceService
from services.aws_service import AWSService


class MainWindow:
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

        self.create_widgets()
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
        self.camera.release()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
