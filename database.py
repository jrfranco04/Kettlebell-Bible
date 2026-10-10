import json
import os
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(APP_DIR, "workouts.json")

# Editable text columns, in the order they are written to the table
TEXT_FIELDS = ("title", "type", "config", "rest", "rounds", "content")


def get_db_path():
    # The built app sets FLET_APP_STORAGE_DATA to a folder that survives app updates.
    # Desktop runs fall back to a local (gitignored) data/ folder.
    storage = os.environ.get("FLET_APP_STORAGE_DATA") or os.path.join(APP_DIR, "data")
    os.makedirs(storage, exist_ok=True)
    return os.path.join(storage, "workouts.db")


def get_db_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ---------------------------------- SETUP ----------------------------------


def _migrate_1(conn):
    # Base table (older installs already have it, so only create when missing)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT,
            config TEXT,
            rest TEXT,
            rounds TEXT,
            content TEXT,
            date_created TEXT
        )
    """)
    # Columns for backup/sync: a stable id, a last-modified time, and soft delete
    columns = {row[1] for row in conn.execute("PRAGMA table_info(workouts)")}
    if "uuid" not in columns:
        conn.execute("ALTER TABLE workouts ADD COLUMN uuid TEXT")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE workouts ADD COLUMN updated_at TEXT")
    if "deleted" not in columns:
        conn.execute("ALTER TABLE workouts ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")

    now = _now()
    for (row_id,) in conn.execute("SELECT id FROM workouts WHERE uuid IS NULL").fetchall():
        conn.execute("UPDATE workouts SET uuid = ? WHERE id = ?", (str(uuid.uuid4()), row_id))
    conn.execute("UPDATE workouts SET updated_at = ? WHERE updated_at IS NULL", (now,))
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_workouts_uuid ON workouts(uuid)")

    # Small key/value table for app state (e.g. whether the seed data was loaded)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


# Each entry upgrades the schema by one version (PRAGMA user_version = position)
MIGRATIONS = [_migrate_1]


@contextmanager
def _transaction(conn):
    # Connection must be opened with isolation_level=None so BEGIN/COMMIT are ours
    conn.execute("BEGIN")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _seed_if_needed(conn, seed_path):
    if conn.execute("SELECT 1 FROM meta WHERE key = 'seeded'").fetchone():
        return
    # Rows in the table (even soft-deleted ones) mean this is an existing library
    has_rows = conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] > 0
    if not has_rows:
        if not os.path.exists(seed_path):
            return  # try again next launch rather than marking an empty seed as done
        with open(seed_path, "r", encoding="utf-8") as f:
            seed = json.load(f)
        today = date.today().isoformat()
        now = _now()
        for workout in seed:
            if not workout.get("title"):
                continue
            conn.execute(
                """
                INSERT INTO workouts
                    (uuid, title, type, config, rest, rounds, content, date_created, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    *(workout.get(field) or "" for field in TEXT_FIELDS),
                    today,
                    now,
                ),
            )
    conn.execute("INSERT INTO meta (key, value) VALUES ('seeded', ?)", (_now(),))


def init_db(seed_path=SEED_FILE):
    """Create/upgrade the database and load the bundled workouts on first run.

    Safe to call on every launch. The seed file is only ever loaded once.
    """
    conn = sqlite3.connect(get_db_path(), isolation_level=None)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RuntimeError(
                f"Database schema v{version} is newer than this app supports "
                f"(v{len(MIGRATIONS)}). Update the app."
            )
        for target, migrate in enumerate(MIGRATIONS, start=1):
            if version >= target:
                continue
            with _transaction(conn):
                migrate(conn)
                conn.execute(f"PRAGMA user_version = {target}")
        with _transaction(conn):
            _seed_if_needed(conn, seed_path)
    finally:
        conn.close()


# ---------------------------------- QUERIES ----------------------------------

_SELECT_COLUMNS = "id, uuid, title, type, config, rest, rounds, content, date_created, updated_at"


def _row_to_dict(row):
    workout = dict(row)
    # Stored NULLs become "" so the UI never has to special-case None
    for field in TEXT_FIELDS:
        workout[field] = workout[field] or ""
    return workout


def fetch_all_workouts():
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM workouts WHERE deleted = 0 "
            "ORDER BY date_created ASC, id ASC"
        ).fetchall()
    # Convert database rows to a list of Python dictionaries
    return [_row_to_dict(row) for row in rows]


def add_workouts(workout_data):
    with closing(get_db_connection()) as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO workouts
                (uuid, title, type, config, rest, rounds, content, date_created, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                *(workout_data.get(field, "") for field in TEXT_FIELDS),
                date.today().isoformat(),
                _now(),
            ),
        )
        return cursor.lastrowid


def update_workout(id, data):
    with closing(get_db_connection()) as conn, conn:
        conn.execute(
            """
            UPDATE workouts
            SET title=?, type=?, config=?, rest=?, rounds=?, content=?, updated_at=?
            WHERE id=? AND deleted=0
            """,
            (*(data.get(field, "") for field in TEXT_FIELDS), _now(), id),
        )


def delete_workout(workout_id):
    # Soft delete: keeps a tombstone so a future sync can propagate the deletion
    with closing(get_db_connection()) as conn, conn:
        conn.execute(
            "UPDATE workouts SET deleted = 1, updated_at = ? WHERE id = ?",
            (_now(), workout_id),
        )


def export_json():
    """Serialize every workout to a JSON string (used for manual backups)."""
    payload = {
        "app": "kettlebell-bible",
        "version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "workouts": fetch_all_workouts(),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
