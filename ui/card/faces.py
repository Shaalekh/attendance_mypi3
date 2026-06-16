import os
import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Directory where this file (faces.py) lives — used to locate profiles.db
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


class ProfileDB:
    """Manages SQLite storage for face profiles."""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or os.path.join(_THIS_DIR, "profiles.db")
        self._connection: sqlite3.Connection | None = None

    # -- connection management --------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(self._db_path)
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA foreign_keys=ON")
                self._connection.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                logger.error("Failed to connect to database: %s", e)
                raise
        return self._connection

    # -- schema -----------------------------------------------------------------

    def init_db(self) -> None:
        try:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS profiles (
                        face_id    TEXT PRIMARY KEY,
                        name       TEXT NOT NULL,
                        hindi_name TEXT,
                        image_url  TEXT,
                        registered_at TEXT
                    )
                """)
                columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(profiles)")
                }
                if "registered_at" not in columns:
                    conn.execute("ALTER TABLE profiles ADD COLUMN registered_at TEXT")
            logger.info("Database initialised successfully.")
        except sqlite3.Error as e:
            logger.error("Failed to initialise database: %s", e)
            raise

    # -- queries ----------------------------------------------------------------

    def get_profile(self, face_id: str) -> sqlite3.Row | None:
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM profiles WHERE face_id = ?", (face_id,)
            )
            return cursor.fetchone()
        except sqlite3.Error as e:
            logger.error("Failed to fetch profile for face_id=%s: %s", face_id, e)
            raise

    def add_profile(
        self,
        face_id: str,
        name: str,
        hindi_name: str | None,
        image_url: str,
        registered_at: str | None = None,
    ) -> None:
        registered_at = registered_at or datetime.now(timezone.utc).isoformat()
        try:
            conn = self._get_connection()
            with conn:  # automatic commit / rollback
                conn.execute(
                    """
                    INSERT INTO profiles (face_id, name, hindi_name, image_url, registered_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (face_id, name, hindi_name, image_url, registered_at),
                )
            logger.info("Profile added for face_id=%s", face_id)
        except sqlite3.IntegrityError:
            logger.warning("Profile already exists for face_id=%s", face_id)
            raise
        except sqlite3.Error as e:
            logger.error("Failed to add profile for face_id=%s: %s", face_id, e)
            raise

    # -- cleanup ----------------------------------------------------------------

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
                logger.info("Database connection closed.")
            except sqlite3.Error as e:
                logger.error("Error closing database connection: %s", e)
            finally:
                self._connection = None

    def __enter__(self):
        self.init_db()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
