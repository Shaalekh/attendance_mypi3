import os
import logging
import tkinter as tk
from PIL import Image, ImageTk
from faces import ProfileDB

logger = logging.getLogger(__name__)

# Directory that sits next to this file
_IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")


class CardUI(tk.Tk):
    """Non-interactive, display-only window for showing a face profile card."""

    # -- default card dimensions ------------------------------------------------
    CARD_WIDTH = 400
    CARD_HEIGHT = 420
    IMAGE_SIZE = (200, 300)

    def __init__(self, profile_db: ProfileDB):
        super().__init__()
        self.title("Face Profile Card")
        self.geometry(f"{self.CARD_WIDTH}x{self.CARD_HEIGHT}")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        self.profile_db = profile_db
        self._photo_ref: ImageTk.PhotoImage | None = None  # prevent GC

        self._create_widgets()

    # -- widget creation --------------------------------------------------------

    def _create_widgets(self) -> None:
        """Build a purely label-based, non-interactive layout."""

        # Profile image
        self.image_label = tk.Label(
            self,
            bg="#1e1e2e",
            width=self.IMAGE_SIZE[0],
            height=self.IMAGE_SIZE[1],
        )
        self.image_label.pack(pady=(20, 10))

        # Name
        self.name_label = tk.Label(
            self,
            text="",
            font=("Arial", 18, "bold"),
            fg="white",
            bg="#1e1e2e",
        )
        self.name_label.pack(pady=(5, 0))

        # Hindi name
        self.hindi_name_label = tk.Label(
            self,
            text="",
            font=("Arial", 14),
            fg="#b0b0b0",
            bg="#1e1e2e",
        )
        self.hindi_name_label.pack(pady=(2, 0))

        # Status bar
        self.status_label = tk.Label(
            self,
            text="No profile loaded",
            font=("Arial", 10, "italic"),
            fg="#888888",
            bg="#1e1e2e",
        )
        self.status_label.pack(side="bottom", pady=(0, 10))

    # -- public API -------------------------------------------------------------

    def load_profile(self, face_id: str) -> None:
        """Fetch a profile from the DB and update all labels (incl. image)."""
        try:
            profile = self.profile_db.get_profile(face_id)
        except Exception:
            logger.exception("Database error while loading profile")
            self._show_error("Database error")
            return

        if profile is None:
            self._show_error(f"Profile not found: {face_id}")
            return

        # -- text labels --------------------------------------------------------
        self.name_label.config(text=profile["name"])
        self.hindi_name_label.config(text=profile["hindi_name"] or "")
        self.status_label.config(text=f"ID: {face_id}", fg="#888888")

        # -- profile image ------------------------------------------------------
        image_url: str | None = profile["image_url"]
        if image_url:
            self._load_image(image_url)
        else:
            self.image_label.config(image="", text="No image", fg="#888888")

    # -- internal helpers -------------------------------------------------------

    def _load_image(self, image_url: str) -> None:
        """Load an image from the images/ directory into the image label."""
        # image_url may be a bare filename or a relative path like "images/foo.jpg"
        path = os.path.join(_IMAGES_DIR, os.path.basename(image_url))

        if not os.path.isfile(path):
            logger.warning("Image file not found: %s", path)
            self.image_label.config(image="", text="Image not found", fg="#888888")
            return

        try:
            img = Image.open(path)
            img = img.resize(self.IMAGE_SIZE, Image.LANCZOS)
            self._photo_ref = ImageTk.PhotoImage(img)
            self.image_label.config(image=self._photo_ref, text="")
        except Exception:
            logger.exception("Failed to load image: %s", path)
            self.image_label.config(image="", text="Image error", fg="#888888")

    def _show_error(self, message: str) -> None:
        """Display an error message in the status bar and clear other fields."""
        self.name_label.config(text="")
        self.hindi_name_label.config(text="")
        self.image_label.config(image="", text="")
        self.status_label.config(text=message, fg="red")


def main():
    with ProfileDB() as db:
        app = CardUI(db)
        app.load_profile("aalekh_babu")
        app.mainloop()


if __name__ == "__main__":
    main()