"""Tests for database.py. Run from the project root: python3 -m unittest discover -s tests"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db  # noqa: E402

LEGACY_SCHEMA = """
    CREATE TABLE workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, type TEXT, config TEXT, rest TEXT,
        rounds TEXT, content TEXT, date_created TEXT
    )
"""

SEED = [
    {
        "id": 1,
        "title": "One",
        "type": "Complex",
        "config": "Single KB",
        "rest": "60 seconds",
        "content": "Swing\nClean",
        "rounds": "5 Rounds",
    },
    {
        "title": "Two",
        "type": "Workout",
        "config": "Mace",
        "rest": "",
        "content": "",
        "rounds": "",
    },
    {"title": "", "type": "skipped: no title"},
]


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.seed_path = os.path.join(self.tmp.name, "seed.json")
        self.write_seed(SEED)

    def write_seed(self, data):
        with open(self.seed_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def raw(self, sql, params=()):
        with closing(sqlite3.connect(db.get_db_path())) as conn, conn:
            return conn.execute(sql, params).fetchall()


class TestSetupAndSeeding(DatabaseTestCase):
    def test_db_lives_in_storage_dir(self):
        self.assertEqual(db.get_db_path(), os.path.join(self.tmp.name, "workouts.db"))

    def test_fresh_install_seeds_workouts(self):
        db.init_db(self.seed_path)
        workouts = db.fetch_all_workouts()
        self.assertEqual(
            [w["title"] for w in workouts], ["One", "Two"]
        )  # untitled skipped
        self.assertEqual(workouts[0]["content"], "Swing\nClean")
        self.assertTrue(all(w["uuid"] and w["updated_at"] for w in workouts))
        self.assertEqual(len({w["uuid"] for w in workouts}), 2)

    def test_init_is_idempotent(self):
        db.init_db(self.seed_path)
        db.init_db(self.seed_path)
        self.assertEqual(len(db.fetch_all_workouts()), 2)

    def test_deleting_everything_does_not_reseed(self):
        db.init_db(self.seed_path)
        for workout in db.fetch_all_workouts():
            db.delete_workout(workout["id"])
        db.init_db(self.seed_path)
        self.assertEqual(db.fetch_all_workouts(), [])

    def test_changed_seed_file_is_ignored_after_first_run(self):
        db.init_db(self.seed_path)
        self.write_seed([{"title": "Brand New"}])
        db.init_db(self.seed_path)
        self.assertEqual([w["title"] for w in db.fetch_all_workouts()], ["One", "Two"])

    def test_missing_seed_file_retries_next_launch(self):
        missing = os.path.join(self.tmp.name, "nope.json")
        db.init_db(missing)
        self.assertEqual(db.fetch_all_workouts(), [])
        db.init_db(self.seed_path)
        self.assertEqual(len(db.fetch_all_workouts()), 2)

    def test_schema_version_is_recorded(self):
        db.init_db(self.seed_path)
        self.assertEqual(self.raw("PRAGMA user_version")[0][0], len(db.MIGRATIONS))

    def test_newer_schema_is_refused(self):
        db.init_db(self.seed_path)
        self.raw(f"PRAGMA user_version = {len(db.MIGRATIONS) + 1}")
        with self.assertRaises(RuntimeError):
            db.init_db(self.seed_path)

    def test_bundled_seed_file_is_valid(self):
        with open(db.SEED_FILE, "r", encoding="utf-8") as f:
            seed = json.load(f)
        self.assertGreater(len(seed), 0)
        self.assertTrue(all(w.get("title") for w in seed))
        db.init_db(db.SEED_FILE)
        self.assertEqual(len(db.fetch_all_workouts()), len(seed))


class TestMigration(DatabaseTestCase):
    def make_legacy_db(self):
        with closing(sqlite3.connect(db.get_db_path())) as conn, conn:
            conn.execute(LEGACY_SCHEMA)
            conn.execute(
                "INSERT INTO workouts (title, type, config, rest, rounds, content, date_created)"
                " VALUES ('Old A','Complex','Single KB','60 seconds','5 Rounds','Swing','2026-01-20')"
            )
            conn.execute(
                "INSERT INTO workouts (title, type, config, rest, rounds, content, date_created)"
                " VALUES ('Old B', NULL, NULL, NULL, NULL, NULL, '2026-01-21')"
            )

    def test_legacy_db_keeps_rows_and_gains_uuids(self):
        self.make_legacy_db()
        db.init_db(self.seed_path)
        workouts = db.fetch_all_workouts()
        self.assertEqual([w["title"] for w in workouts], ["Old A", "Old B"])
        self.assertEqual(workouts[0]["date_created"], "2026-01-20")
        self.assertTrue(all(w["uuid"] and w["updated_at"] for w in workouts))
        self.assertEqual(len({w["uuid"] for w in workouts}), 2)

    def test_existing_library_is_not_seeded(self):
        self.make_legacy_db()
        db.init_db(self.seed_path)
        self.assertNotIn("One", [w["title"] for w in db.fetch_all_workouts()])

    def test_null_columns_come_back_as_empty_strings(self):
        self.make_legacy_db()
        db.init_db(self.seed_path)
        old_b = db.fetch_all_workouts()[1]
        for field in db.TEXT_FIELDS[1:]:
            self.assertEqual(old_b[field], "")

    def test_failed_migration_rolls_back(self):
        db.init_db(self.seed_path)
        version = len(db.MIGRATIONS)

        def broken(conn):
            conn.execute("ALTER TABLE workouts ADD COLUMN half_done TEXT")
            raise ValueError("boom")

        with mock.patch.object(db, "MIGRATIONS", db.MIGRATIONS + [broken]):
            with self.assertRaises(ValueError):
                db.init_db(self.seed_path)
        self.assertEqual(self.raw("PRAGMA user_version")[0][0], version)
        columns = [row[1] for row in self.raw("PRAGMA table_info(workouts)")]
        self.assertNotIn("half_done", columns)
        self.assertEqual(len(db.fetch_all_workouts()), 2)


class TestCrud(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        db.init_db(self.seed_path)

    def new(self, **overrides):
        data = {
            "title": "Mine",
            "type": "Workout",
            "config": "Single KB",
            "rest": "90 seconds",
            "content": "Press",
            "rounds": "3 Rounds",
        }
        data.update(overrides)
        return db.add_workouts(data)

    def test_add_appears_last_with_uuid(self):
        new_id = self.new()
        workouts = db.fetch_all_workouts()
        self.assertEqual(workouts[-1]["id"], new_id)
        self.assertEqual(workouts[-1]["title"], "Mine")
        self.assertTrue(workouts[-1]["uuid"])

    def test_add_tolerates_missing_fields(self):
        db.add_workouts({"title": "Only a title"})
        workout = db.fetch_all_workouts()[-1]
        self.assertEqual(workout["rest"], "")
        self.assertEqual(workout["content"], "")

    def test_update_changes_fields_and_timestamp_but_not_uuid(self):
        new_id = self.new()
        before = db.fetch_all_workouts()[-1]
        db.update_workout(
            new_id,
            {
                "title": "Renamed",
                "type": "EMOM",
                "config": "Mace",
                "rest": "",
                "content": "Swing",
                "rounds": "10",
            },
        )
        after = db.fetch_all_workouts()[-1]
        self.assertEqual(after["title"], "Renamed")
        self.assertEqual(after["config"], "Mace")
        self.assertEqual(after["uuid"], before["uuid"])
        self.assertGreaterEqual(after["updated_at"], before["updated_at"])

    def test_delete_hides_workout_but_keeps_tombstone(self):
        new_id = self.new()
        db.delete_workout(new_id)
        self.assertNotIn(new_id, [w["id"] for w in db.fetch_all_workouts()])
        rows = self.raw("SELECT deleted FROM workouts WHERE id = ?", (new_id,))
        self.assertEqual(rows, [(1,)])

    def test_update_does_not_resurrect_deleted_workout(self):
        new_id = self.new()
        db.delete_workout(new_id)
        db.update_workout(new_id, {"title": "Zombie"})
        self.assertNotIn("Zombie", [w["title"] for w in db.fetch_all_workouts()])

    def test_export_json_contains_workouts_and_metadata(self):
        self.new()
        payload = json.loads(db.export_json())
        self.assertEqual(payload["app"], "kettlebell-bible")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(len(payload["workouts"]), 3)
        self.assertIn("uuid", payload["workouts"][0])


if __name__ == "__main__":
    unittest.main()
