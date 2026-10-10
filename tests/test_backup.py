"""Tests for backup.py. Run from the project root: python3 -m unittest discover -s tests"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backup import (  # noqa: E402
    MAX_BACKUP_BYTES,
    BackupError,
    ParsedBackup,
    describe_import,
    describe_result,
    load_backup,
    parse_backup,
)


def export_file(workouts, **extra):
    data = {
        "app": "kettlebell-bible",
        "version": 1,
        "exported_at": "2026-10-09T21:00:00",
    }
    data.update(extra)
    data["workouts"] = workouts
    return json.dumps(data)


class TestParseBackup(unittest.TestCase):
    def test_reads_an_export(self):
        parsed = parse_backup(
            export_file(
                [
                    {
                        "uuid": "a",
                        "title": "One",
                        "type": "Complex",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    }
                ]
            )
        )
        self.assertEqual(len(parsed.workouts), 1)
        self.assertEqual(parsed.workouts[0]["uuid"], "a")
        self.assertEqual(parsed.workouts[0]["rest"], "")  # missing text becomes ""
        self.assertEqual(parsed.exported_at, "2026-10-09T21:00:00")
        self.assertEqual(parsed.invalid, 0)

    def test_reads_bytes_with_a_byte_order_mark(self):
        raw = b"\xef\xbb\xbf" + export_file([{"title": "One"}]).encode("utf-8")
        self.assertEqual(len(parse_backup(raw).workouts), 1)

    def test_reads_a_plain_list_like_workouts_json(self):
        parsed = parse_backup(
            json.dumps([{"id": 1, "title": "One"}, {"id": 2, "title": "Two"}])
        )
        self.assertEqual([w["title"] for w in parsed.workouts], ["One", "Two"])

    def test_old_export_without_uuids_or_version(self):
        old = json.dumps(
            {
                "app": "kettlebell-bible",
                "exported_at": "x",
                "workouts": [{"id": 3, "title": "Old"}],
            }
        )
        parsed = parse_backup(old)
        self.assertEqual(parsed.workouts[0]["uuid"], "")

    def test_skips_unusable_entries_and_counts_them(self):
        parsed = parse_backup(
            export_file(
                [
                    {"title": "Good"},
                    {"title": "   "},
                    {"type": "no title"},
                    "junk",
                    5,
                    None,
                ]
            )
        )
        self.assertEqual([w["title"] for w in parsed.workouts], ["Good"])
        self.assertEqual(parsed.invalid, 5)

    def test_non_text_values_are_converted(self):
        parsed = parse_backup(export_file([{"title": "T", "rounds": 5, "rest": None}]))
        self.assertEqual(parsed.workouts[0]["rounds"], "5")
        self.assertEqual(parsed.workouts[0]["rest"], "")

    def test_duplicate_uuid_keeps_the_newest_copy(self):
        parsed = parse_backup(
            export_file(
                [
                    {
                        "uuid": "a",
                        "title": "New",
                        "updated_at": "2026-05-01T00:00:00+00:00",
                    },
                    {
                        "uuid": "a",
                        "title": "Old",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    },
                    {"uuid": "b", "title": "Other"},
                ]
            )
        )
        self.assertEqual([w["title"] for w in parsed.workouts], ["New", "Other"])

    def test_rejects_non_json(self):
        with self.assertRaisesRegex(BackupError, "isn't valid JSON"):
            parse_backup("this is not json {")

    def test_rejects_binary(self):
        with self.assertRaisesRegex(BackupError, "isn't a text file"):
            parse_backup(b"\xff\xfe\x00\x80\x81")

    def test_rejects_json_that_is_not_a_backup(self):
        for text in (
            '{"hello": "world"}',
            '"just a string"',
            "42",
            '{"workouts": "nope"}',
            "null",
        ):
            with self.assertRaisesRegex(BackupError, "doesn't look like"):
                parse_backup(text)

    def test_rejects_other_apps_backups(self):
        with self.assertRaisesRegex(BackupError, "different app"):
            parse_backup(json.dumps({"app": "something-else", "workouts": []}))

    def test_rejects_newer_versions(self):
        with self.assertRaisesRegex(BackupError, "newer version"):
            parse_backup(export_file([{"title": "x"}], version=2))
        with self.assertRaisesRegex(BackupError, "newer version"):
            parse_backup(export_file([{"title": "x"}], version="two"))

    def test_rejects_huge_files(self):
        with self.assertRaisesRegex(BackupError, "too big"):
            parse_backup(b" " * (MAX_BACKUP_BYTES + 1))

    def test_empty_backup_is_valid(self):
        self.assertEqual(parse_backup(export_file([])).workouts, [])


class TestLoadBackup(unittest.TestCase):
    def test_loads_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "backup.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(export_file([{"title": "One"}]))
            self.assertEqual(len(load_backup(path).workouts), 1)

    def test_missing_file_gives_a_friendly_error(self):
        with self.assertRaisesRegex(BackupError, "Couldn't read that file"):
            load_backup("/nonexistent/folder/backup.json")


class TestDescriptions(unittest.TestCase):
    def counts(self, **overrides):
        base = dict(
            added=0, updated=0, unchanged=0, kept_newer=0, deleted_here=0, restored=0
        )
        base.update(overrides)
        return base

    def test_only_non_zero_lines_and_plurals(self):
        lines = describe_import(
            self.counts(added=1, updated=2, unchanged=3, kept_newer=1, deleted_here=4),
            ParsedBackup(invalid=2),
        )
        self.assertEqual(
            lines,
            [
                "1 new workout will be added",
                "2 workouts will be updated (the backup has a newer version)",
                "3 already up to date",
                "1 left alone (your copy is newer)",
                "4 you deleted after this backup was made",
                "2 unreadable entries ignored",
            ],
        )

    def test_nothing_to_say(self):
        self.assertEqual(describe_import(self.counts(), ParsedBackup()), [])

    def test_result_sentence(self):
        self.assertEqual(
            describe_result(self.counts(added=3, updated=1, restored=2)),
            "Imported: 3 added, 1 updated, 2 restored",
        )
        self.assertEqual(describe_result(self.counts()), "Nothing was imported")


if __name__ == "__main__":
    unittest.main()
