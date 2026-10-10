"""Pure helper functions for the UI (no Flet imports, so they are easy to test)."""

import math
import re
import time

# Workout fields the search box looks through
SEARCH_FIELDS = ("title", "type", "rest", "rounds")


def format_time(total_seconds):
    mins, sec = divmod(int(total_seconds), 60)
    return f"{mins:02d}:{sec:02d}"


def parse_count(text):
    """Turn the round counter's text into a whole number >= 0 (anything else is 0)."""
    try:
        return max(0, int(str(text).strip()))
    except ValueError:
        return 0


def config_tags(config):
    """'Single KB, Double KB' -> ['Single KB', 'Double KB']"""
    return [tag.strip() for tag in (config or "").split(",") if tag.strip()]


def config_options(workouts):
    """Every distinct equipment/config tag in the library, for the filter dropdown."""
    tags = {tag for w in workouts for tag in config_tags(w.get("config"))}
    return sorted(tags, key=str.lower)


def filter_workouts(workouts, config="All", text=""):
    """Apply the equipment dropdown and the search box (both optional)."""
    result = workouts

    if config and config != "All":
        wanted = config.lower()
        result = [
            w
            for w in result
            if wanted in [t.lower() for t in config_tags(w.get("config"))]
        ]

    text = (text or "").strip().lower()
    if text:
        result = [
            w
            for w in result
            if any(text in (w.get(field) or "").lower() for field in SEARCH_FIELDS)
        ]

    return result


# ------------------------------- timers -------------------------------

DEFAULT_REST_SECONDS = 60  # Used when a workout's rest text has no usable number

_NUMBER = r"\d+(?:\.\d+)?"
_UNIT = r"(?:seconds?|secs?|s|minutes?|mins?|m)\b"
_RANGE = re.compile(rf"({_NUMBER})\s*(?:-|\u2013|to)\s*({_NUMBER})\s*({_UNIT})?")
_AMOUNT = re.compile(rf"({_NUMBER})\s*({_UNIT})")
_CLOCK = re.compile(r"^\s*(\d+)?:(\d{2})\s*$")
_JOINER = re.compile(r"^\s*(?:and)?\s*$")


def _unit_seconds(unit):
    return 60 if unit.startswith("m") else 1


def parse_seconds(text):
    """Read a rest/interval time from workout text, in whole seconds (None if there isn't one).

    '90 Seconds' -> 90, '2 minutes' -> 120, '1:30' -> 90, ':30' -> 30, '90' -> 90,
    '1 min 30 sec' -> 90. A range uses its lower number: '60-90 seconds' -> 60.
    Text with no number ('As needed', 'Remaining Time', '') gives None.
    """
    text = (text or "").strip().lower()
    if not text:
        return None

    clock = _CLOCK.match(text)
    if clock:
        seconds = int(clock.group(1) or 0) * 60 + int(clock.group(2))
        return seconds or None

    if re.fullmatch(_NUMBER, text):
        return round(float(text)) or None

    ranged = _RANGE.search(text)
    if ranged:
        unit = ranged.group(3) or "s"
        return round(float(ranged.group(1)) * _unit_seconds(unit)) or None

    total, last_end = 0.0, None
    for match in _AMOUNT.finditer(text):
        # Only add amounts that directly follow each other, like '1 min 30 sec'
        if last_end is not None and not _JOINER.match(text[last_end : match.start()]):
            break
        total += float(match.group(1)) * _unit_seconds(match.group(2))
        last_end = match.end()
    return round(total) or None


def format_countdown(target, elapsed):
    """Countdown text and whether time is up: '01:30' counting down, then '+00:07' over."""
    remaining = target - elapsed
    if remaining > 0:
        return format_time(math.ceil(remaining)), False
    over = int(-remaining)
    return ("+" + format_time(over) if over else format_time(0)), True


class ElapsedClock:
    """Counts elapsed time with a monotonic clock, so it stays right if the UI lags
    or the phone sleeps. `now` can be swapped for a fake clock in tests."""

    def __init__(self, now=time.monotonic):
        self._now = now
        self._base = 0.0  # time banked from earlier runs
        self._started = None  # clock reading when it last began running

    @property
    def running(self):
        return self._started is not None

    def elapsed(self):
        if self._started is None:
            return self._base
        return self._base + (self._now() - self._started)

    def start(self):
        if self._started is None:
            self._started = self._now()

    def pause(self):
        if self._started is not None:
            self._base = self.elapsed()
            self._started = None

    def reset(self):
        self._base = 0.0
        self._started = None


# ----------------------------- interval timer -----------------------------

DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_INTERVAL_COUNT = 10
MAX_INTERVAL_COUNT = 99

_EVERY_N_MOM = re.compile(r"\be(\d+)mom\b")
_EVERY_N_MINUTES = re.compile(r"\bevery\s+(\d+)\s+min")
_ROUNDS = re.compile(r"(\d+)(?:\s*-\s*\d+)?\s*rounds?\b")
_BARE_COUNT = re.compile(r"^\s*(\d+)(?:\s*-\s*\d+)?\s*$")


def _interval_length(workout):
    label = " ".join(str(workout.get(f) or "") for f in ("title", "type", "config"))
    label = label.lower()
    content = (workout.get("content") or "").lower()
    for source, pattern in ((label, _EVERY_N_MOM), (content, _EVERY_N_MINUTES)):
        found = pattern.search(source)
        if found and int(found.group(1)) > 0:
            return int(found.group(1)) * 60
    return DEFAULT_INTERVAL_SECONDS  # EMOM, or anything else: every minute


def interval_defaults(workout):
    """(seconds per interval, number of intervals) to start the interval timer with.

    EMOM is every 60s and E2MOM every 120s. The count comes from the workout's
    rounds text: '20 Minutes' fills the time with intervals ('12-20 Minutes' uses the
    lower number), '5 Rounds' means 5, and anything else gets 10.
    """
    interval = _interval_length(workout)
    rounds = (workout.get("rounds") or "").lower()

    count = None
    if re.search(r"\bmin", rounds):
        total = parse_seconds(rounds)
        if total:
            count = max(1, total // interval)
    if not count:
        found = _ROUNDS.search(rounds) or _BARE_COUNT.match(rounds)
        count = int(found.group(1)) if found else None
    if not count:
        count = DEFAULT_INTERVAL_COUNT
    return interval, max(1, min(MAX_INTERVAL_COUNT, count))


def interval_progress(elapsed, interval, count):
    """Where the interval timer is: (0-based interval index, seconds left in it, done?)."""
    if elapsed >= interval * count:
        return count - 1, 0.0, True
    index = int(elapsed // interval)
    return index, interval - (elapsed - index * interval), False
