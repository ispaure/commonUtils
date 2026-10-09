"""Shared wheel gestures for discrete page readers; settings reload on each event."""
from time import monotonic
from . import pyside as qt
from ..settings import get_wheel_navigation_settings


class PageWheel:
    def __init__(self):
        self.delta = 0
        self.last_turn = 0
        self.last_event = 0
        self.pixels = None

    def direction(self, event, *, now=None, settings=None):
        """Return -1/1 for a page turn, otherwise zero. Callers consume the event."""
        if event.modifiers():
            return 0
        now = monotonic() if now is None else now
        settings = settings or get_wheel_navigation_settings()
        pixels = not event.pixelDelta().isNull()
        delta = event.pixelDelta().y() if pixels else event.angleDelta().y()
        if not delta:
            return 0
        notch = not pixels and event.phase() == qt.Qt.ScrollPhase.NoScrollPhase
        if notch and settings.immediate_notches:
            self.delta = 0
            self.last_turn = now
            return -1 if delta > 0 else 1
        if now - self.last_turn < settings.cooldown_ms / 1000:
            self.delta = 0
            return 0
        if now - self.last_event > 1 or self.delta * delta < 0 or self.pixels != pixels:
            self.delta = 0
        self.pixels = pixels
        self.last_event = now
        self.delta += delta
        if abs(self.delta) < (60 if pixels else 120) / settings.sensitivity:
            return 0
        direction = -1 if self.delta > 0 else 1
        self.delta = 0
        self.last_turn = now
        return direction
