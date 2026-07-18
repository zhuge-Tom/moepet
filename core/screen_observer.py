"""Opt-in scheduler for occasional desktop observations.

The scheduler never captures a screen itself.  It only asks its owner to do so,
which keeps consent, capture lifetime, and model routing in one place.
"""

import random

from PySide6.QtCore import QObject, QTimer, Signal


class ScreenObserver(QObject):
    observation_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.observation_requested)
        self._min_seconds = 300
        self._max_seconds = 900
        self._enabled = False

    def configure(self, enabled: bool, min_seconds: int, max_seconds: int) -> None:
        self._timer.stop()
        self._enabled = bool(enabled)
        self._min_seconds = max(60, int(min_seconds))
        self._max_seconds = max(self._min_seconds, int(max_seconds))
        if self._enabled:
            self.schedule_next()

    def schedule_next(self) -> None:
        if not self._enabled:
            return
        delay_ms = random.randint(self._min_seconds, self._max_seconds) * 1000
        self._timer.start(delay_ms)

    def stop(self) -> None:
        self._enabled = False
        self._timer.stop()
