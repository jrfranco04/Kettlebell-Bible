"""Tests for merging backups into the library (database.import_workouts)."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db  # noqa: E402
from backup import parse_backup  # noqa: E402
from test_database import SEED, DatabaseTestCase  # noqa: E402

OLD = "2026-01-01T00:00:00.000+00:00"
MID = "2026-06-01T00:00:00.000+00:00"
NEW = "2026-12-01T00:00:00.000+00:00"


def incoming(title="One", uuid="", updated_at="", **fields):
    workout = {
        "title": title,
        "type": "",
        "config": "",
        "rest": "",
        "rounds": "",
        "content": "",
    }
    workout.update(fields)
    workout.update(uuid=uuid, updated_at=updated_at, date_created="")
    return workout


class ImportTestCase(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        db.init_db(self.seed_path)  # library = "One", "Two"

    def library(self):
        return {w["title"]: w for w in db.fetch_all_workouts()}

    def stamp(self, title, when):
        """Pin a library workout's updated_at so tests don't depend on the clock."""
        self.raw("UPDATE workouts SET updated_at = ? WHERE title = ?", (when, title))


class TestMergeRules(ImportTestCase):
    def test_new_workout_is_added_with_its_uuid_and_timestamp(self):
        counts = db.import_workouts(
            [incoming("Fresh", uuid="u-1", updated_at=MID, rounds="3")]
        )
        self.assertEqual(counts["added"], 1)
        fresh = self.library()["Fresh"]
        self.assertEqual(
            (fresh["uuid"], fresh["updated_at"], fresh["rounds"]), ("u-1", MID, "3")
        )
        self.assertEqual(len(db.fetch_all_workouts()), 3)

    def test_newer_backup_copy_updates_the_library(self):
        uuid = self.library()["One"]["uuid"]
        self.stamp("One", MID)
        counts = db.import_workouts(
            [incoming("One (edited)", uuid=uuid, updated_at=NEW)]
        )
        self.assertEqual(counts["updated"], 1)
        edited = self.library()["One (edited)"]
        self.assertEqual((edited["uuid"], edited["updated_at"]), (uuid, NEW))

    def test_older_backup_copy_is_left_alone(self):
        uuid = self.library()["One"]["uuid"]
        self.stamp("One", NEW)
        counts = db.import_workouts([incoming("Stale name", uuid=uuid, updated_at=MID)])
        self.assertEqual(counts["kept_newer"], 1)
        self.assertIn("One", self.library())
        self.assertNotIn("Stale name", self.library())

    def test_same_timestamp_different_text_keeps_the_library_copy(self):
        uuid = self.library()["One"]["uuid"]
        self.stamp("One", MID)
        counts = db.import_workouts([incoming("Other text", uuid=uuid, updated_at=MID)])
        self.assertEqual(counts["kept_newer"], 1)
        self.assertIn("One", self.library())

    def test_identical_copy_is_unchanged(self):
        mine = self.library()["One"]
        same = incoming(
            **{
                k: mine[k]
                for k in ("title", "type", "config", "rest", "rounds", "content")
            },
            uuid=mine["uuid"],
            updated_at=NEW,
        )
        counts = db.import_workouts([same])
        self.assertEqual(counts["unchanged"], 1)
        self.assertEqual(
            self.library()["One"]["updated_at"], mine["updated_at"]
        )  # untouched

    def test_missing_timestamp_never_overwrites(self):
        uuid = self.library()["One"]["uuid"]
        counts = db.import_workouts([incoming("Changed", uuid=uuid, updated_at="")])
        self.assertEqual(counts["kept_newer"], 1)
        self.assertIn("One", self.library())

    def test_unreadable_timestamp_on_new_workout_gets_the_current_time(self):
        db.import_workouts([incoming("Fresh", uuid="u-2", updated_at="garbage")])
        self.assertTrue(db.parse_timestamp(self.library()["Fresh"]["updated_at"]))

    def test_importing_twice_changes_nothing_the_second_time(self):
        batch = [incoming("Fresh", uuid="u-3", updated_at=MID), incoming("Plain")]
        first = db.import_workouts(batch)
        second = db.import_workouts(batch)
        self.assertEqual(
            (first["added"], second["added"], second["unchanged"]), (2, 0, 2)
        )
        self.assertEqual(len(db.fetch_all_workouts()), 4)

    def test_duplicate_entries_in_one_batch_do_not_duplicate_or_crash(self):
        counts = db.import_workouts(
            [incoming("Dup", uuid="u-4"), incoming("Dup", uuid="u-4")]
        )
        self.assertEqual((counts["added"], counts["unchanged"]), (1, 1))
        self.assertEqual(len(db.fetch_all_workouts()), 3)


class TestOldBackupsWithoutUuids(ImportTestCase):
    def test_matches_existing_workouts_by_text(self):
        mine = self.library()["One"]
        same = incoming(
            **{
                k: mine[k]
                for k in ("title", "type", "config", "rest", "rounds", "content")
            }
        )
        counts = db.import_workouts([same, incoming("Brand New")])
        self.assertEqual((counts["unchanged"], counts["added"]), (1, 1))
        self.assertEqual(len(db.fetch_all_workouts()), 3)

    def test_gets_a_fresh_uuid(self):
        db.import_workouts([incoming("Legacy")])
        self.assertTrue(self.library()["Legacy"]["uuid"])


class TestDeletedWorkouts(ImportTestCase):
    def setUp(self):
        super().setUp()
        mine = self.library()["One"]
        self.one_uuid = mine["uuid"]
        self.backup_copy = incoming(
            **{
                k: mine[k]
                for k in ("title", "type", "config", "rest", "rounds", "content")
            },
            uuid=mine["uuid"],
            updated_at=mine["updated_at"],
        )
        db.delete_workout(mine["id"])

    def test_skipped_by_default(self):
        counts = db.import_workouts([self.backup_copy])
        self.assertEqual((counts["deleted_here"], counts["restored"]), (1, 0))
        self.assertNotIn("One", self.library())

    def test_lists_the_deleted_workouts_so_they_can_be_offered(self):
        counts = db.import_workouts([self.backup_copy], dry_run=True)
        self.assertEqual(counts["deleted"], [{"uuid": self.one_uuid, "title": "One"}])

    def test_restored_when_chosen(self):
        counts = db.import_workouts([self.backup_copy], restore=[self.one_uuid])
        self.assertEqual((counts["restored"], counts["deleted_here"]), (1, 0))
        self.assertIn("One", self.library())

    def test_choosing_an_unrelated_uuid_restores_nothing(self):
        counts = db.import_workouts([self.backup_copy], restore=["not-a-real-uuid"])
        self.assertEqual((counts["restored"], counts["deleted_here"]), (0, 1))
        self.assertNotIn("One", self.library())

    def test_restored_copy_is_not_deleted_again_by_a_second_import(self):
        db.import_workouts([self.backup_copy], restore=[self.one_uuid])
        counts = db.import_workouts([self.backup_copy])
        self.assertEqual(counts["unchanged"] + counts["kept_newer"], 1)
        self.assertIn("One", self.library())

    def test_old_backup_without_uuids_also_finds_the_deleted_one(self):
        no_uuid = dict(self.backup_copy, uuid="", updated_at="")
        preview = db.import_workouts([no_uuid], dry_run=True)
        self.assertEqual(preview["deleted_here"], 1)
        # restoring uses the library's uuid for it, which the preview reports
        chosen = [d["uuid"] for d in preview["deleted"]]
        self.assertEqual(db.import_workouts([no_uuid], restore=chosen)["restored"], 1)
        self.assertIn("One", self.library())

    def test_same_deleted_workout_listed_twice_in_a_file_counts_once(self):
        no_uuid = dict(self.backup_copy, uuid="", updated_at="")
        counts = db.import_workouts([no_uuid, no_uuid])
        self.assertEqual((counts["deleted_here"], len(counts["deleted"])), (1, 1))
        chosen = [self.one_uuid]
        counts = db.import_workouts([no_uuid, no_uuid], restore=chosen)
        self.assertEqual(counts["restored"], 1)


class TestRestoreKeepsTheRightVersion(ImportTestCase):
    def backup_of(self, title):
        mine = self.library()[title]
        return incoming(
            **{
                k: mine[k]
                for k in ("title", "type", "config", "rest", "rounds", "content")
            },
            uuid=mine["uuid"],
            updated_at=mine["updated_at"],
        )

    def test_edit_made_after_the_backup_survives_delete_and_restore(self):
        backup = self.backup_of("One")
        one = self.library()["One"]
        db.update_workout(
            one["id"],
            {
                "title": "One (edited)",
                "type": "",
                "config": "",
                "rest": "",
                "rounds": "",
                "content": "",
            },
        )
        db.delete_workout(one["id"])
        db.import_workouts([backup], restore=[one["uuid"]])
        self.assertIn("One (edited)", self.library())
        self.assertNotIn("One", self.library())

    def test_backup_edit_made_after_the_deletion_wins(self):
        one = self.library()["One"]
        db.delete_workout(one["id"])
        newer = incoming(
            "One (edited elsewhere)",
            uuid=one["uuid"],
            updated_at="2999-01-01T00:00:00+00:00",
        )
        db.import_workouts([newer], restore=[one["uuid"]])
        restored = self.library()["One (edited elsewhere)"]
        self.assertEqual(restored["updated_at"], "2999-01-01T00:00:00+00:00")


class TestChoosingWhichDeletedToRestore(ImportTestCase):
    def test_restores_only_the_ticked_ones(self):
        db.add_workouts({"title": "Three"})
        db.add_workouts({"title": "Four"})
        backup = [
            incoming(
                **{
                    k: w[k]
                    for k in ("title", "type", "config", "rest", "rounds", "content")
                },
                uuid=w["uuid"],
                updated_at=w["updated_at"],
            )
            for w in db.fetch_all_workouts()
        ]
        by_title = self.library()
        accidental, intended = by_title["One"], by_title["Three"]
        for w in (accidental, intended, by_title["Four"]):
            db.delete_workout(w["id"])

        preview = db.import_workouts(backup, dry_run=True)
        self.assertEqual(preview["deleted_here"], 3)
        self.assertEqual(
            sorted(d["title"] for d in preview["deleted"]), ["Four", "One", "Three"]
        )

        result = db.import_workouts(backup, restore=[accidental["uuid"]])
        self.assertEqual((result["restored"], result["deleted_here"]), (1, 2))
        self.assertEqual(
            sorted(self.library()), ["One", "Two"]
        )  # Three and Four stay deleted


class TestDryRun(ImportTestCase):
    def test_reports_counts_but_changes_nothing(self):
        uuid = self.library()["One"]["uuid"]
        self.stamp("One", OLD)
        before = db.fetch_all_workouts()
        batch = [
            incoming("Fresh", uuid="u-5"),
            incoming("One v2", uuid=uuid, updated_at=NEW),
        ]
        preview = db.import_workouts(batch, dry_run=True)
        self.assertEqual((preview["added"], preview["updated"]), (1, 1))
        self.assertEqual(db.fetch_all_workouts(), before)
        # ...and the real run gives the same numbers
        self.assertEqual(db.import_workouts(batch), preview)


class TestAtomicity(ImportTestCase):
    def test_failure_part_way_rolls_back_everything(self):
        batch = [incoming("Fine", uuid="u-6"), incoming("Bad", uuid="u-7")]
        real_now = db._now
        calls = {"n": 0}

        def flaky_now():
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk on fire")
            return real_now()

        before = db.fetch_all_workouts()
        with mock.patch.object(db, "_now", flaky_now):
            with self.assertRaises(RuntimeError):
                db.import_workouts(batch)
        self.assertEqual(db.fetch_all_workouts(), before)


class TestRoundTrip(ImportTestCase):
    def snapshot(self):
        return sorted(
            (
                w["uuid"],
                w["title"],
                w["type"],
                w["config"],
                w["rest"],
                w["rounds"],
                w["content"],
                w["updated_at"],
            )
            for w in db.fetch_all_workouts()
        )

    def test_export_then_import_into_an_empty_library_is_identical(self):
        db.add_workouts(
            {"title": "Mine", "type": "Workout", "content": "line1\nline2 • ü"}
        )
        exported = db.export_json()
        original = self.snapshot()

        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        with mock.patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": other}):
            db.init_db(os.path.join(other, "no-seed.json"))  # empty: no seed file here
            parsed = parse_backup(exported)
            counts = db.import_workouts(parsed.workouts)
            self.assertEqual(counts["added"], len(original))
            self.assertEqual(self.snapshot(), original)
            # and importing it again is a no-op
            again = db.import_workouts(parse_backup(exported).workouts)
            self.assertEqual((again["added"], again["updated"]), (0, 0))

    def test_edit_on_one_device_flows_to_the_other(self):
        exported_before = db.export_json()
        one = self.library()["One"]
        db.update_workout(
            one["id"],
            {
                "title": "One (heavier)",
                "type": "",
                "config": "",
                "rest": "",
                "rounds": "",
                "content": "",
            },
        )
        exported_after = db.export_json()

        # a library that still has the old copy picks up the edit
        db.update_workout(
            one["id"],
            {
                "title": "One",
                "type": "Complex",
                "config": "Single KB",
                "rest": "60 seconds",
                "content": "Swing\nClean",
                "rounds": "5 Rounds",
            },
        )
        self.stamp("One", MID)
        counts = db.import_workouts(parse_backup(exported_after).workouts)
        self.assertEqual(counts["updated"], 1)
        self.assertIn("One (heavier)", self.library())
        # while the older backup would not undo it
        counts = db.import_workouts(parse_backup(exported_before).workouts)
        self.assertEqual(counts["updated"], 0)
        self.assertIn("One (heavier)", self.library())

    def test_phase_zero_export_format_imports_cleanly(self):
        phase_zero = (
            '{"app": "kettlebell-bible", "exported_at": "2026-10-09T20:00:00", "workouts": ['
            '{"id": 1, "title": "One", "type": "Complex", "config": "Single KB", "rest": "60 seconds",'
            ' "rounds": "5 Rounds", "content": "Swing\\nClean", "date_created": "2026-01-20"},'
            '{"id": 2, "title": "Only In Backup", "type": "", "config": "", "rest": "", "rounds": "",'
            ' "content": "", "date_created": "2026-01-20"}]}'
        )
        counts = db.import_workouts(parse_backup(phase_zero).workouts)
        self.assertEqual((counts["unchanged"], counts["added"]), (1, 1))
        self.assertEqual(self.library()["Only In Backup"]["date_created"], "2026-01-20")


if __name__ == "__main__":
    unittest.main()
