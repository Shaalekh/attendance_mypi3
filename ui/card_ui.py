"""card_ui.py – Non-interactive profile-card overlay for the attendance system.

Design goals (Raspberry Pi 3 / startx environment):
- SQLite is opened **once** on a dedicated daemon thread so the Tkinter
  event loop is never blocked by I/O.
- ``load_profile(face_id)`` is safe to call from *any* thread (camera /
  AWS worker threads).  It simply drops a message onto a lock-free queue.
- The card window is a borderless ``tk.Toplevel`` that appears for exactly
  ``CARD_DURATION_MS`` milliseconds and then withdraws itself.
- The database path is resolved relative to this file so the script can be
  started from any working directory without accidentally creating a second
  ``profiles.db`` elsewhere.
"""

import os
import queue
import sqlite3
import threading
import tkinter as tk
from PIL import Image, ImageTk


# ---------------------------------------------------------------------------
# Resolve database path relative to the project root (parent of ui/)
# ---------------------------------------------------------------------------
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_UI_DIR)
DB_PATH = os.path.join(_PROJECT_ROOT, "profiles.db")

# Card visible duration (milliseconds)
CARD_DURATION_MS = 3000

# Seconds to wait for the background DB thread to exit cleanly on shutdown
DB_THREAD_SHUTDOWN_TIMEOUT = 2

# Profile photo size expected in the database
PHOTO_WIDTH = 200
PHOTO_HEIGHT = 300


class CardUI:
    """Borderless profile-card overlay driven by a background SQLite thread.

    Lifecycle::

        card = CardUI(root)          # start background thread + build window
        card.load_profile("abc123")  # schedule DB lookup (non-blocking)
        ...
        card.destroy()               # graceful shutdown
    """

    CARD_WIDTH = 340
    CARD_HEIGHT = 460

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._window: tk.Toplevel | None = None
        self._hide_job: str | None = None

        # SimpleQueue is thread-safe and has no maximum size – ideal for
        # one-way producer→consumer messaging without GIL contention.
        self._db_queue: queue.SimpleQueue = queue.SimpleQueue()

        self._db_thread = threading.Thread(
            target=self._db_worker, daemon=True, name="CardUI-DB"
        )
        self._db_thread.start()

        self._build_window()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_profile(self, face_id: str) -> None:
        """Schedule a profile lookup for *face_id* (thread-safe, non-blocking)."""
        self._db_queue.put(face_id)

    def destroy(self) -> None:
        """Shut down the background thread and destroy the overlay window."""
        self._db_queue.put(None)          # sentinel tells worker to exit
        self._db_thread.join(timeout=DB_THREAD_SHUTDOWN_TIMEOUT)
        if self._window:
            self._window.destroy()
            self._window = None

    # ------------------------------------------------------------------
    # Window construction (called once on the main thread)
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)        # no title bar or borders
        win.withdraw()                    # hidden until a profile is loaded

        # Centre on screen
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - self.CARD_WIDTH) // 2
        y = (sh - self.CARD_HEIGHT) // 2
        win.geometry(f"{self.CARD_WIDTH}x{self.CARD_HEIGHT}+{x}+{y}")

        bg = "#1a1a2e"
        win.configure(bg=bg)

        # Photo placeholder
        self._img_label = tk.Label(win, bg=bg)
        self._img_label.pack(pady=(20, 10))

        # Name
        self._name_label = tk.Label(
            win,
            text="",
            font=("Arial", 16, "bold"),
            fg="white",
            bg=bg,
        )
        self._name_label.pack()

        # Department / extra info
        self._info_label = tk.Label(
            win,
            text="",
            font=("Arial", 11),
            fg="#aaaacc",
            bg=bg,
            justify="center",
        )
        self._info_label.pack(pady=(6, 20))

        self._window = win

    # ------------------------------------------------------------------
    # Background DB worker (runs on CardUI-DB thread)
    # ------------------------------------------------------------------

    def _db_worker(self) -> None:
        """Keep one SQLite connection alive; process face_id requests."""
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            _ensure_schema(conn)

            while True:
                face_id = self._db_queue.get()   # blocks until work arrives
                if face_id is None:              # sentinel → shutdown
                    break
                try:
                    row = _fetch_profile(conn, face_id)
                    # Hand result back to the Tkinter event loop
                    self._root.after(0, self._show_card, row)
                except sqlite3.Error as exc:
                    print(f"[CardUI] DB error while loading '{face_id}': {exc}")
        except Exception as exc:
            print(f"[CardUI] Fatal DB thread error: {exc}")
        finally:
            if conn:
                conn.close()

    # ------------------------------------------------------------------
    # Card display helpers (must run on the main thread via root.after)
    # ------------------------------------------------------------------

    def _show_card(self, row: sqlite3.Row | None) -> None:
        if row is None or self._window is None:
            return

        name = row["name"]
        dept = row["dept"] or ""
        photo_url = row["photo_url"] or ""

        self._name_label.config(text=name)
        self._info_label.config(text=dept)

        # Reset photo
        self._img_label.config(image="")
        self._img_label.image = None  # type: ignore[attr-defined]

        if photo_url and os.path.isfile(photo_url):
            try:
                img = Image.open(photo_url).resize(
                    (PHOTO_WIDTH, PHOTO_HEIGHT), Image.LANCZOS
                )
                tk_img = ImageTk.PhotoImage(img)
                self._img_label.config(image=tk_img)
                self._img_label.image = tk_img  # keep reference alive
            except Exception as exc:
                print(f"[CardUI] Could not load photo '{photo_url}': {exc}")

        # Cancel any pending auto-hide from a previous card
        if self._hide_job is not None:
            self._root.after_cancel(self._hide_job)

        self._window.deiconify()
        self._window.lift()
        self._hide_job = self._root.after(CARD_DURATION_MS, self._hide_card)

    def _hide_card(self) -> None:
        if self._window:
            self._window.withdraw()
        self._hide_job = None


# ---------------------------------------------------------------------------
# SQLite helpers (module-level so they are easy to unit-test)
# ---------------------------------------------------------------------------

def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the profiles table if it does not already exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            face_id   TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            dept      TEXT    DEFAULT '',
            photo_url TEXT    DEFAULT ''
        )
        """
    )
    conn.commit()


def _fetch_profile(conn: sqlite3.Connection, face_id: str) -> sqlite3.Row | None:
    """Return the profile row for *face_id*, or ``None`` if not found."""
    cur = conn.execute(
        "SELECT name, dept, photo_url FROM profiles WHERE face_id = ?",
        (face_id,),
    )
    return cur.fetchone()
