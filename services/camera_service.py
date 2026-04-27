class CameraService:
    def __init__(self):
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "picamera2 is not installed. Install python3-picamera2 (apt) "
                "or picamera2 (pip)."
            ) from exc

        self.picam2 = Picamera2()
        try:
            config = self.picam2.create_preview_configuration(
                main={"size": (640, 480)}
            )

            self.picam2.configure(config)
            self.picam2.start()
        except Exception as exc:
            raise RuntimeError(f"Failed to initialise Pi camera: {exc}") from exc

    def get_frame(self):
        frame = self.picam2.capture_array()
        return frame

    def release(self):
        self.picam2.stop()
