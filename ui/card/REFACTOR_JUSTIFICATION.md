# Refactor Justification — `faces.py`

## Original Code

```python
import sqlite3

connection = sqlite3.connect('profiles.db')

def init_db():
    with connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS profiles (...)''')

def get_profile(face_id):
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM profiles WHERE face_id = ?', (face_id,))
    return cursor.fetchone()

def add_profile(face_id, name, hindi_name, image_url):
    with connection:
        connection.execute('''INSERT INTO profiles (...) VALUES (?, ?, ?, ?)''',
                           (face_id, name, hindi_name, image_url))
```

---

## Problems with the Original

| # | Issue | Impact |
|---|-------|--------|
| 1 | **Module-level connection** — `sqlite3.connect()` runs at import time. | The DB file is opened even if no database work is needed, and the connection can never be reconfigured or swapped. |
| 2 | **No error handling** — every function lets exceptions propagate silently. | A corrupt DB or disk-full condition crashes the app with an unhelpful traceback; no log trail for debugging. |
| 3 | **No transaction safety on reads** — `get_profile` creates a raw cursor outside a `with` block. | If the connection is in an inconsistent state, reads can surface stale or partial data. |
| 4 | **No duplicate-insert protection** — `add_profile` doesn't distinguish `IntegrityError`. | A duplicate `face_id` raises a generic error; callers can't tell *why* the insert failed. |
| 5 | **Global mutable state** — the connection is a module-level variable shared by all callers. | Hard to test, hard to run two instances (e.g. in-memory DB for tests vs on-disk for prod). |
| 6 | **Connection never closed** — there is no `close()` call anywhere. | On long-running processes (like a Raspberry Pi kiosk) this can leak file handles and cause locking issues. |
| 7 | **No type hints** — function signatures give no indication of expected types. | IDE auto-complete and static analysers can't catch type mistakes. |

---

## How the Refactored Code Addresses Each Issue

### 1. Lazy Connection (`_get_connection`)

The connection is created **only when first needed**, not at import time. This avoids side effects during module loading and lets you instantiate `ProfileDB` with different paths (e.g. `:memory:` for tests).

### 2. Comprehensive Error Handling

Every method wraps database calls in `try/except sqlite3.Error`, logs the failure with context (face_id, operation), and re-raises so callers can still react. This gives you a complete audit trail without swallowing errors.

### 3. Transactions Everywhere

- **Writes** use `with conn:` which auto-commits on success and auto-rolls-back on any exception.
- **Reads** go through the same managed connection, keeping behaviour predictable.

### 4. Explicit `IntegrityError` Handling

`add_profile` catches `sqlite3.IntegrityError` separately and logs a clear warning (`"Profile already exists for face_id=…"`). Callers can catch this specific exception to show a user-friendly message instead of a stack trace.

### 5. Encapsulation via Class

All state lives inside a `ProfileDB` instance. You can create multiple instances pointing at different databases, pass them via dependency injection, and mock them easily in tests.

### 6. Proper Resource Cleanup

- `close()` method for explicit cleanup.
- Context-manager support (`with ProfileDB() as db: …`) guarantees the connection is closed even if an exception occurs.

### 7. Type Hints & Logging

- Full type annotations on every method.
- `logging` module replaces silent failures — messages include the operation and the relevant `face_id` for traceability.

### 8. SQLite Performance Pragmas

- **WAL mode** (`PRAGMA journal_mode=WAL`) allows concurrent reads while a write is in progress — important on a Pi running a camera loop.
- **`sqlite3.Row` factory** gives dict-like access (`row["name"]`) instead of fragile tuple indexing (`row[1]`).

---

## Before / After Comparison

| Aspect | Original | Refactored |
|--------|----------|------------|
| Structure | Loose functions + global variable | Single `ProfileDB` class |
| Connection lifetime | Opened at import, never closed | Lazy open, explicit close / context manager |
| Error handling | None | `try/except` with logging on every operation |
| Transaction safety | Partial (writes only) | Full (`with conn:` on all writes) |
| Duplicate detection | Generic crash | `IntegrityError` caught and logged |
| Testability | Requires monkeypatching module global | Instantiate with `:memory:` DB |
| Type safety | No hints | Full annotations |
| Logging | None | `logging` with contextual messages |
| Concurrency | Default journal mode | WAL mode for better read/write concurrency |
| Row access | Tuple indexing | `sqlite3.Row` (dict-like) |
