"""Tests for the timer helpers in helpers.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import (  # noqa: E402
    DEFAULT_REST_SECONDS,
    ElapsedClock,
    format_countdown,
    parse_seconds,
)


class TestParseSeconds(unittest.TestCase):
    def check(self, cases):
        for text, expected in cases:
            self.assertEqual(parse_seconds(text), expected, repr(text))

    def test_the_values_in_the_library(self):
        self.check(
            [
                ("90 Seconds", 90),
                ("60 seconds", 60),
                ("120 Seconds", 120),
                ("90 seconds", 90),
                ("60-90 seconds", 60),  # a range starts at its lower number
            ]
        )

    def test_text_with_no_usable_number(self):
        self.check(
            [
                ("As needed", None),
                ("Remaining Time", None),
                ("", None),
                (None, None),
                ("   ", None),
            ]
        )

    def test_minutes_and_clock_formats(self):
        self.check(
            [
                ("2 minutes", 120),
                ("1 min", 60),
                ("1.5 min", 90),
                ("1:30", 90),
                (":30", 30),
                ("2:00", 120),
                ("1 min 30 sec", 90),
                ("1 minute and 30 seconds", 90),
            ]
        )

    def test_bare_numbers_and_short_units(self):
        self.check([("90", 90), (" 45 ", 45), ("75s", 75), ("30 sec", 30)])

    def test_ranges(self):
        self.check(
            [
                ("60 to 90 sec", 60),
                ("1-2 minutes", 60),
                ("45 - 60 seconds", 45),
                ("60–90 seconds", 60),
                ("60-90", 60),
            ]
        )

    def test_zero_is_not_a_preset(self):
        self.check([("0", None), ("0 seconds", None), (":00", None)])

    def test_picks_the_time_out_of_surrounding_words(self):
        self.check([("3 sets, 90 seconds", 90), ("rest 90 seconds between rounds", 90)])

    def test_separate_amounts_are_not_added_together(self):
        self.assertEqual(parse_seconds("90 seconds, 2 minutes between rounds"), 90)

    def test_default_rest_is_a_sensible_number(self):
        self.assertEqual(DEFAULT_REST_SECONDS, 60)


class TestFormatCountdown(unittest.TestCase):
    def test_counts_down_rounding_up(self):
        self.assertEqual(format_countdown(90, 0), ("01:30", False))
        self.assertEqual(format_countdown(90, 0.2), ("01:30", False))
        self.assertEqual(format_countdown(90, 30), ("01:00", False))
        self.assertEqual(format_countdown(90, 89.5), ("00:01", False))

    def test_reaches_zero_then_counts_the_overtime(self):
        self.assertEqual(format_countdown(90, 90), ("00:00", True))
        self.assertEqual(format_countdown(90, 90.9), ("00:00", True))
        self.assertEqual(format_countdown(90, 91), ("+00:01", True))
        self.assertEqual(format_countdown(90, 97.4), ("+00:07", True))
        self.assertEqual(format_countdown(60, 60 + 125), ("+02:05", True))

    def test_zero_target_is_immediately_up(self):
        self.assertEqual(format_countdown(0, 0), ("00:00", True))


class FakeNow:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class TestElapsedClock(unittest.TestCase):
    def setUp(self):
        self.now = FakeNow()
        self.clock = ElapsedClock(self.now)

    def test_starts_stopped_at_zero(self):
        self.assertFalse(self.clock.running)
        self.assertEqual(self.clock.elapsed(), 0)

    def test_counts_while_running(self):
        self.clock.start()
        self.now.advance(7.5)
        self.assertTrue(self.clock.running)
        self.assertEqual(self.clock.elapsed(), 7.5)

    def test_pause_freezes_and_resume_continues(self):
        self.clock.start()
        self.now.advance(10)
        self.clock.pause()
        self.now.advance(500)  # time passing while paused doesn't count
        self.assertEqual(self.clock.elapsed(), 10)
        self.clock.start()
        self.now.advance(5)
        self.assertEqual(self.clock.elapsed(), 15)

    def test_start_twice_does_not_restart(self):
        self.clock.start()
        self.now.advance(4)
        self.clock.start()
        self.now.advance(4)
        self.assertEqual(self.clock.elapsed(), 8)

    def test_pause_twice_is_harmless(self):
        self.clock.start()
        self.now.advance(3)
        self.clock.pause()
        self.clock.pause()
        self.assertEqual(self.clock.elapsed(), 3)

    def test_reset_stops_and_clears(self):
        self.clock.start()
        self.now.advance(30)
        self.clock.reset()
        self.assertFalse(self.clock.running)
        self.assertEqual(self.clock.elapsed(), 0)
        self.now.advance(30)
        self.assertEqual(self.clock.elapsed(), 0)

    def test_catches_up_after_a_long_gap(self):
        # e.g. the screen was off and no ticks ran for a while
        self.clock.start()
        self.now.advance(600)
        self.assertEqual(self.clock.elapsed(), 600)


if __name__ == "__main__":
    unittest.main()
