"""Tests for helpers.py. Run from the project root: python3 -m unittest discover -s tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import (  # noqa: E402
    config_options,
    config_tags,
    filter_workouts,
    format_time,
    parse_count,
)

WORKOUTS = [
    {
        "title": "Swing/Clean",
        "type": "KB Complex",
        "config": "Single KB",
        "rest": "90 Seconds",
        "rounds": "5 Rounds",
    },
    {
        "title": "Double Press",
        "type": "KB Workout",
        "config": "Double KB",
        "rest": "As needed",
        "rounds": "3 Rounds",
    },
    {
        "title": "Mace Flow",
        "type": "Complex",
        "config": "Mace",
        "rest": "",
        "rounds": "4-5",
    },
    {
        "title": "Mixed Day",
        "type": "KB Workout",
        "config": "Single KB, Double KB, Mace",
        "rest": None,
        "rounds": None,
    },
    {
        "title": "Minute Work",
        "type": "EMOM",
        "config": "EMOM",
        "rest": "Remaining Time",
        "rounds": "20 Minutes",
    },
    {
        "title": "Every Other",
        "type": "E2MOM",
        "config": "E2MOM",
        "rest": "",
        "rounds": "",
    },
]


def titles(workouts):
    return [w["title"] for w in workouts]


class TestFormatTime(unittest.TestCase):
    def test_formats_minutes_and_seconds(self):
        self.assertEqual(format_time(0), "00:00")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(600), "10:00")

    def test_over_an_hour_keeps_counting_minutes(self):
        self.assertEqual(format_time(75 * 60 + 3), "75:03")

    def test_fractional_seconds_are_floored(self):
        self.assertEqual(format_time(59.9), "00:59")


class TestParseCount(unittest.TestCase):
    def test_valid_numbers(self):
        self.assertEqual(parse_count("7"), 7)
        self.assertEqual(parse_count(" 12 "), 12)

    def test_bad_input_becomes_zero(self):
        for text in ("", "  ", "abc", "1.5", None):
            self.assertEqual(parse_count(text), 0, repr(text))

    def test_never_negative(self):
        self.assertEqual(parse_count("-3"), 0)


class TestConfigTags(unittest.TestCase):
    def test_splits_and_trims(self):
        self.assertEqual(
            config_tags("Single KB,  Double KB , Mace"),
            ["Single KB", "Double KB", "Mace"],
        )

    def test_empty_and_none(self):
        self.assertEqual(config_tags(""), [])
        self.assertEqual(config_tags(None), [])

    def test_options_are_distinct_and_sorted(self):
        self.assertEqual(
            config_options(WORKOUTS),
            ["Double KB", "E2MOM", "EMOM", "Mace", "Single KB"],
        )

    def test_options_ignore_missing_config(self):
        self.assertEqual(
            config_options([{"title": "x"}, {"title": "y", "config": None}]), []
        )


class TestFilterWorkouts(unittest.TestCase):
    def test_no_filters_returns_everything(self):
        self.assertEqual(filter_workouts(WORKOUTS), WORKOUTS)
        self.assertEqual(filter_workouts(WORKOUTS, "All", ""), WORKOUTS)

    def test_dropdown_matches_combined_configs(self):
        self.assertEqual(
            titles(filter_workouts(WORKOUTS, "Single KB")), ["Swing/Clean", "Mixed Day"]
        )
        self.assertEqual(
            titles(filter_workouts(WORKOUTS, "Mace")), ["Mace Flow", "Mixed Day"]
        )

    def test_emom_does_not_match_e2mom(self):
        self.assertEqual(titles(filter_workouts(WORKOUTS, "EMOM")), ["Minute Work"])
        self.assertEqual(titles(filter_workouts(WORKOUTS, "E2MOM")), ["Every Other"])

    def test_search_is_case_insensitive_and_trimmed(self):
        self.assertEqual(
            titles(filter_workouts(WORKOUTS, text="  MACE ")), ["Mace Flow"]
        )

    def test_search_covers_type_rest_and_rounds(self):
        self.assertEqual(
            titles(filter_workouts(WORKOUTS, text="e2mom")), ["Every Other"]
        )
        self.assertEqual(
            titles(filter_workouts(WORKOUTS, text="as needed")), ["Double Press"]
        )
        self.assertEqual(titles(filter_workouts(WORKOUTS, text="4-5")), ["Mace Flow"])

    def test_missing_fields_do_not_crash_search(self):
        # 'Mixed Day' has None for rest and rounds
        self.assertEqual(titles(filter_workouts(WORKOUTS, text="mixed")), ["Mixed Day"])
        self.assertEqual(filter_workouts(WORKOUTS, text="zzz"), [])

    def test_dropdown_and_search_combine(self):
        self.assertEqual(
            titles(filter_workouts(WORKOUTS, "Single KB", "swing")), ["Swing/Clean"]
        )
        self.assertEqual(filter_workouts(WORKOUTS, "Mace", "swing"), [])


if __name__ == "__main__":
    unittest.main()
