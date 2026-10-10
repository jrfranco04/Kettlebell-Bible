"""The timer panel on a workout page: a Stopwatch and a Rest countdown."""

import asyncio
import logging

import flet as ft

from helpers import (
    DEFAULT_REST_SECONDS,
    ElapsedClock,
    format_countdown,
    format_time,
    parse_seconds,
)

log = logging.getLogger(__name__)

STOPWATCH, REST = "stopwatch", "rest"
ADJUST_STEP = 15  # Seconds the -/+ buttons add to or remove from the rest
MIN_REST = 5
FLASHES = 3


class TimerPanel:
    """Builds the timer UI (`layout`) and runs it.

    Each mode keeps its own clock. Switching modes pauses the one you leave without
    clearing it; only Reset clears. Time comes from a monotonic clock, not from
    counting ticks, so the display stays right if the UI lags or the screen sleeps.

    keep_awake(True/False) is called as a timer starts and stops running, and
    `haptic` is used (together with a screen flash) when the rest is up.
    """

    def __init__(self, page, keep_awake, haptic, rest_text=""):
        self.page = page
        self.keep_awake = keep_awake
        self.haptic = haptic

        # A workout whose rest has no number in it ("As needed") gets the default
        preset = parse_seconds(rest_text)
        self.has_rest_preset = preset is not None
        self.rest_target = preset or DEFAULT_REST_SECONDS

        self.mode = STOPWATCH
        self.clocks = {STOPWATCH: ElapsedClock(), REST: ElapsedClock()}
        self.alerted = False  # The "time's up" alert has already fired for this rest
        self._task = None
        self._alert_task = None
        self._closed = False
        self._haptics_work = True
        self._build()
        self._render()

    @property
    def clock(self):
        return self.clocks[self.mode]

    # ---------------------------------- UI ----------------------------------

    def _build(self):
        self.mode_selector = ft.SegmentedButton(
            selected=[STOPWATCH],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=STOPWATCH, label="Stopwatch"),
                ft.Segment(value=REST, label="Rest"),
            ],
            on_change=self._on_mode_change,
        )
        self.status = ft.Text("", size=10, weight=ft.FontWeight.BOLD)
        self.time_display = ft.Text(
            "00:00", size=40, weight=ft.FontWeight.BOLD, font_family="monospace"
        )
        self.adjust_row = ft.Row(
            [
                ft.Button(f"−{ADJUST_STEP}s", on_click=self._on_less),
                ft.Button(f"+{ADJUST_STEP}s", on_click=self._on_more),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )
        self.play_btn = ft.IconButton(
            icon=ft.Icons.PLAY_ARROW,
            icon_size=60,
            on_click=self._on_play,
            icon_color=ft.Colors.GREEN,
        )
        self.pause_btn = ft.IconButton(
            icon=ft.Icons.PAUSE,
            icon_size=60,
            on_click=self._on_pause,
            visible=False,
            icon_color=ft.Colors.AMBER,
        )
        self.reset_btn = ft.IconButton(
            icon=ft.Icons.REPLAY_ROUNDED,
            icon_size=60,
            on_click=self._on_reset,
            icon_color=ft.Colors.RED,
        )
        self.card = ft.Container(
            border_radius=10,
            padding=10,
            content=ft.Column(
                [
                    self.status,
                    self.time_display,
                    ft.Divider(),
                    self.adjust_row,
                    ft.Row(
                        [self.play_btn, self.pause_btn, self.reset_btn],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.layout = ft.Column(
            [self.mode_selector, self.card],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _display(self):
        """(time text, is the rest up?) for the current mode."""
        if self.mode == REST:
            return format_countdown(self.rest_target, self.clock.elapsed())
        return format_time(self.clock.elapsed()), False

    def _render(self):
        """Copies the current state onto the controls (caller does the page update)."""
        text, time_up = self._display()
        self.time_display.value = text
        self.time_display.color = ft.Colors.GREEN if time_up else None
        if self.mode == REST:
            self.status.value = "GO!" if time_up else "REST"
        else:
            self.status.value = "STOPWATCH"
        self.status.color = ft.Colors.GREEN if time_up else ft.Colors.OUTLINE
        self.play_btn.visible = not self.clock.running
        self.pause_btn.visible = self.clock.running
        self.adjust_row.visible = self.mode == REST
        self.mode_selector.selected = [self.mode]

    def _refresh(self):
        # Safe to call from the timer task: once the page is gone there is nothing to do
        try:
            self.card.update()
        except RuntimeError:
            return False
        return True

    # ------------------------------ running it ------------------------------

    def _start(self):
        if self.clock.running:
            return
        self.clock.start()
        self._task = self.page.run_task(self._loop)
        self.keep_awake(True)

    def _stop_running(self):
        """Pauses whichever clock is running (its time is kept)."""
        self.clock.pause()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.keep_awake(False)

    def _clear_alert(self):
        if self._alert_task is not None:
            self._alert_task.cancel()
            self._alert_task = None
        self.card.bgcolor = None

    def _reset_current(self):
        self._stop_running()
        self.clock.reset()
        if self.mode == REST:
            self.alerted = False
        self._clear_alert()

    async def _loop(self):
        clock = self.clock  # Only the mode that was started runs; switching pauses it
        shown = None
        while clock.running and not self._closed:
            text, time_up = self._display()
            if self.mode == REST and time_up and not self.alerted:
                self.alerted = True
                self._alert_task = self.page.run_task(self._alert)
            if (text, time_up) != shown:
                shown = (text, time_up)
                self._render()
                if not self._refresh():
                    return
            await asyncio.sleep(0.2)

    async def _buzz(self):
        if not self._haptics_work:
            return
        try:
            await self.haptic.vibrate()
            await self.haptic.heavy_impact()
        except Exception as ex:  # Not every device/platform supports it
            self._haptics_work = False
            log.warning("Haptic feedback isn't available: %s", ex)

    async def _alert(self):
        """Vibrates and flashes the panel so the end of the rest is hard to miss."""
        for _ in range(FLASHES):
            self.card.bgcolor = ft.Colors.GREEN_700
            if not self._refresh():
                return
            await self._buzz()
            await asyncio.sleep(0.25)
            self.card.bgcolor = None
            if not self._refresh():
                return
            await asyncio.sleep(0.25)

    # ---------------------------- what the user does ----------------------------

    def set_mode(self, mode):
        if mode == self.mode:
            return
        self._stop_running()  # Pause what was running; it keeps its time
        self._clear_alert()
        self.mode = mode
        self._render()
        self.page.update()

    def start_rest(self):
        """Begins a fresh rest countdown (used when a round is marked done)."""
        if self.mode != REST:
            self.set_mode(REST)
        self._reset_current()
        self._start()
        self._render()
        self.page.update()

    def adjust_rest(self, seconds):
        self.rest_target = max(MIN_REST, self.rest_target + seconds)
        if self.clocks[REST].elapsed() < self.rest_target:
            self.alerted = False  # Extended past where it stands, so alert again
            self._clear_alert()
        self._render()
        self.page.update()

    def stop(self):
        """Halts everything for good (called when leaving the workout page)."""
        self._closed = True
        for clock in self.clocks.values():
            clock.pause()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._clear_alert()
        self.keep_awake(False)

    def _on_play(self, e):
        self._start()
        self._render()
        self.page.update()

    def _on_pause(self, e):
        self._stop_running()
        self._render()
        self.page.update()

    def _on_reset(self, e):
        self._reset_current()
        self._render()
        self.page.update()

    def _on_mode_change(self, e):
        selected = e.control.selected
        if selected:
            self.set_mode(selected[0])

    def _on_less(self, e):
        self.adjust_rest(-ADJUST_STEP)

    def _on_more(self, e):
        self.adjust_rest(ADJUST_STEP)
