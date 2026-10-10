"""Reading and checking backup files (the JSON made by Export backup)."""

import json
from dataclasses import dataclass, field

from database import TEXT_FIELDS, parse_timestamp

APP_NAME = "kettlebell-bible"
SUPPORTED_VERSION = 1
MAX_BACKUP_BYTES = 5 * 1024 * 1024  # a real library is a few dozen KB


class BackupError(Exception):
    """A problem with a backup file. The message is safe to show to the user."""


@dataclass
class ParsedBackup:
    workouts: list = field(default_factory=list)
    exported_at: str = ""
    invalid: int = 0  # entries that were skipped because they were unusable


def load_backup(path):
    """Read a backup file from disk and check it."""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_BACKUP_BYTES + 1)
    except OSError as ex:
        raise BackupError(f"Couldn't read that file ({ex.strerror or ex}).") from ex
    return parse_backup(raw)


def parse_backup(raw):
    """Check backup contents (bytes or text) and return the usable workouts.

    Accepts the export format ({"workouts": [...]}) and a plain list of workouts
    (the same shape as workouts.json). Raises BackupError with a plain-English
    message if the file can't be used.
    """
    if isinstance(raw, bytes):
        if len(raw) > MAX_BACKUP_BYTES:
            raise BackupError("That file is too big to be a workout backup.")
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as ex:
            raise BackupError(
                "That isn't a text file, so it can't be a backup."
            ) from ex

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as ex:
        raise BackupError(
            "That file isn't valid JSON, so it can't be a backup."
        ) from ex

    exported_at = ""
    if isinstance(data, dict):
        if data.get("app") not in (None, APP_NAME):
            raise BackupError("That backup was made by a different app.")
        version = data.get("version", 1)
        if not isinstance(version, int) or version > SUPPORTED_VERSION:
            raise BackupError(
                "That backup was made by a newer version of the app. "
                "Update the app and try again."
            )
        entries = data.get("workouts")
        exported_at = data.get("exported_at") or ""
    else:
        entries = data

    if not isinstance(entries, list):
        raise BackupError("That doesn't look like a Kettlebell Bible backup.")

    workouts, invalid = [], 0
    for entry in entries:
        workout = _clean_entry(entry)
        if workout is None:
            invalid += 1
        else:
            workouts.append(workout)

    return ParsedBackup(_dedupe(workouts), str(exported_at), invalid)


def _clean_entry(entry):
    if not isinstance(entry, dict):
        return None
    workout = {}
    for name in TEXT_FIELDS:
        value = entry.get(name)
        workout[name] = "" if value is None else str(value)
    if not workout["title"].strip():
        return None  # A workout needs a title
    workout["title"] = workout["title"].strip()
    for name in ("uuid", "updated_at", "date_created"):
        value = entry.get(name)
        workout[name] = value.strip() if isinstance(value, str) else ""
    return workout


def _dedupe(workouts):
    """If a file lists the same uuid twice, keep the most recently updated copy."""
    newest, order = {}, []
    for workout in workouts:
        key = workout["uuid"]
        if not key:
            order.append(workout)
            continue
        if key not in newest:
            newest[key] = workout
            order.append(workout)
            continue
        current = newest[key]
        stamp = parse_timestamp(workout["updated_at"])
        current_stamp = parse_timestamp(current["updated_at"])
        if stamp and (current_stamp is None or stamp > current_stamp):
            order[order.index(current)] = workout
            newest[key] = workout
    return order


def _plural(count, singular, plural=None):
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def describe_import(counts, parsed):
    """Plain-English lines for the confirmation dialog (zero counts are left out)."""
    lines = []
    if counts["added"]:
        lines.append(f"{_plural(counts['added'], 'new workout')} will be added")
    if counts["updated"]:
        lines.append(
            f"{_plural(counts['updated'], 'workout')} will be updated "
            "(the backup has a newer version)"
        )
    if counts["unchanged"]:
        lines.append(f"{counts['unchanged']} already up to date")
    if counts["kept_newer"]:
        lines.append(f"{counts['kept_newer']} left alone (your copy is newer)")
    if counts["deleted_here"]:
        lines.append(f"{counts['deleted_here']} you deleted after this backup was made")
    if parsed.invalid:
        lines.append(f"{parsed.invalid} unreadable entries ignored")
    return lines


def describe_result(counts):
    """One short sentence about what an import did."""
    parts = []
    for key, label in (
        ("added", "added"),
        ("updated", "updated"),
        ("restored", "restored"),
    ):
        if counts[key]:
            parts.append(f"{counts[key]} {label}")
    return "Imported: " + ", ".join(parts) if parts else "Nothing was imported"
