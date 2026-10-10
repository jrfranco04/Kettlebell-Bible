"""Pure helper functions for the UI (no Flet imports, so they are easy to test)."""

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
