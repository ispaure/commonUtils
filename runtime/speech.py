"""Bounded utterances, UTF-16 ranges and session-owned native read-aloud."""

from bisect import bisect_left, bisect_right
from time import monotonic
from .speech_text import SpeechText, PROSE_DASH, dash_padding, word_ranges, utf16_length


class PlaybackTimer:
    """A listening-time budget, independent of utterances and playback speed."""

    def __init__(self, loop, *, changed, expired, clock=monotonic):
        self.loop, self.changed, self.expired, self.clock = (
            loop,
            changed,
            expired,
            clock,
        )
        self.duration = self.remaining = 0
        self.running = False
        self.deadline = None
        self.handle = None

    def select(self, seconds):
        self.duration = seconds
        self.reset()

    def reset(self):
        self._cancel()
        self.remaining = self.duration
        self.deadline = (
            self.clock() + self.remaining if self.running and self.duration else None
        )
        self._tick()

    def set_running(self, running):
        if running == self.running:
            return
        if self.deadline is not None:
            self.remaining = max(0, self.deadline - self.clock())
        self._cancel()
        self.running = running
        # A deliberate Play after expiry starts a fresh listening period.
        if running and self.duration and self.remaining <= 0:
            self.remaining = self.duration
        self.deadline = (
            self.clock() + self.remaining if running and self.duration else None
        )
        self._tick()

    def _cancel(self):
        if self.handle is not None:
            self.handle.cancel()
            self.handle = None

    def _tick(self):
        self.handle = None
        if self.deadline is not None:
            self.remaining = max(0, self.deadline - self.clock())
        self.changed(self.remaining)
        if self.deadline is not None:
            if self.remaining <= 0:
                self.deadline = None
                self.running = False
                self.expired()
            else:
                self.handle = self.loop.call_later(min(1, self.remaining), self._tick)

    def dispose(self):
        self._cancel()
        self.running = False
        self.deadline = None


def utterances(text, start=0, end=None, *, limit=1000, breaks=(), sentence_breaks=True):
    """Keep browser offsets intact, including astral characters and block edges."""
    units = [0]
    budget = [0]
    dashes = {match.start() for match in PROSE_DASH.finditer(text)}
    for index, char in enumerate(text):
        units.append(units[-1] + utf16_length(char))
        padding = sum(dash_padding(text, index)) if index in dashes else 0
        budget.append(budget[-1] + utf16_length(char) + padding)
    left = bisect_left(units, max(0, start))
    right = bisect_left(
        units, units[-1] if end is None else min(units[-1], max(start, end))
    )
    boundaries = set(breaks)
    while left < right:
        while left < right and text[left].isspace():
            left += 1
        if left >= right:
            break
        stop = left + 1
        while stop < right and budget[stop + 1] - budget[left] <= limit:
            if units[stop] in boundaries or (
                sentence_breaks and text[stop - 1] in ".!?。！？" and text[stop].isspace()
            ):
                break
            stop += 1
        if (
            stop < right
            and units[stop] not in boundaries
            and text[stop - 1] not in ".!?。！？"
            and not text[stop - 1].isspace()
        ):
            space = text.rfind(" ", left + 1, stop)
            if space >= left + (stop - left) // 2:
                stop = space + 1
        yield text[left:stop], units[left], units[stop]
        left = stop


class SpeechSession:
    def __init__(self, engine, *, on_range, on_state, clock=monotonic):
        self.clock = clock
        self.engine, self.on_range, self.on_state = engine, on_range, on_state
        self.can_speak = lambda: True
        self.on_finished = lambda: None
        self.closed, self.state, self.generation = False, "stopped", 0
        self.ranges, self.index = [], 0
        self.text, self.words, self.breaks = "", [], ()
        self.elapsed = 0
        self.native_paused = False
        engine.completed = self.completed
        engine.failed = self.failed
        engine.progress = self.progress
        engine.started = self.started
        self.word_timer = None
        self.spoken = None

    def utterances(self, text, start=0, end=None, *, breaks=()):
        return utterances(text, start, end, breaks=breaks,
                          limit=getattr(self.engine, 'utterance_limit', 1000),
                          sentence_breaks=getattr(self.engine, 'sentence_breaks', True))

    def play(self, text, start=0, end=None, *, voice="", speed=1, breaks=()):
        if self.closed:
            return
        self.stop()
        if not self.engine.ready:
            self.on_state(
                "unavailable", self.engine.error or "Speech engine is starting."
            )
            return
        self.text, self.start, self.end, self.breaks = text, start, end, breaks
        self.words = [left for left, _ in word_ranges(text)
                      if left >= start and (end is None or left < end)]
        self.ranges = list(self.utterances(text, start, end, breaks=breaks))
        self.voice, self.speed, self.index = voice, speed, 0
        if self.ranges:
            self.state = "speaking"
            self.next()
        else:
            self.finish()

    def finish(self):
        """Natural exhaustion only; hosts may lazily supply another document."""
        self.stop()
        generation = self.generation
        self.on_state("stopped", "Finished the selected passage or current chapter.")
        if not self.closed and generation == self.generation:
            self.on_finished()

    def next(self):
        if self.closed or self.state != "speaking":
            return
        if not self.can_speak():
            self.stop()
            return
        if self.index >= len(self.ranges):
            self.finish()
            return
        text, start, end = self.ranges[self.index]
        self.spoken = SpeechText(text)
        self.utterance_words = list(word_ranges(text, start))
        self.cancel_timer()
        self.native_progress = False
        self.position = start
        self.generation += 1
        self.token = str(self.generation)
        try:
            self.started_at = self.clock()
            self.elapsed = 0
            self.on_state("speaking", "Reading aloud · current word highlighted")
            # Preparing media controls may synchronously revoke the route/session.
            # Do not submit audio after a reentrant pause, stop or permission loss.
            if self.closed or self.state != "speaking":
                return
            if not self.can_speak():
                self.stop()
                return
            self.engine.speak(self.spoken.text, self.voice, self.speed, self.token)
        except Exception:
            self.stop()
            self.on_state(
                "unavailable", "Speech failed. Check the installed offline voice."
            )

    def cancel_timer(self):
        if self.word_timer is not None:
            self.word_timer.cancel()
            self.word_timer = None

    def started(self, token):
        if self.closed or self.state != "speaking" or token != self.token:
            return
        self.started_at = self.clock()
        if self.utterance_words:
            self.on_range(*self.utterance_words[0])
        if not self.native_progress and not getattr(
            self.engine, "native_word_events", False
        ):
            self.estimated_word(token, 0)

    def estimated_word(self, token, index):
        if (
            self.closed
            or self.state != "speaking"
            or token != self.token
            or self.native_progress
            or index >= len(self.utterance_words)
        ):
            return
        self.word_timer = None
        self.position = self.utterance_words[index][0]
        self.on_range(*self.utterance_words[index])
        loop = getattr(self.engine, "loop", None)
        if loop is not None and index + 1 < len(self.utterance_words):
            delay = 1 / (3 * self.speed)
            # Give engines time to deliver their first audio-synchronized range.
            self.word_timer = loop.call_later(
                max(0.75, delay) if index == 0 else delay,
                self.estimated_word,
                token,
                index + 1,
            )

    def progress(self, token, start, end):
        if self.closed or self.state != "speaking" or token != self.token:
            return
        _, base, _ = self.ranges[self.index]
        mapped = self.spoken.source_range(start, end)
        if mapped is None:
            return
        left, right = (base + value for value in mapped)
        # Some engines include punctuation or multiple words in their ranges.
        # Publish a single source word, never a dash-joined phrase or padding.
        word = next(((a, b) for a, b in self.utterance_words
                     if a < right and b > left), None)
        if word is None:
            return
        left, right = max(left, word[0]), min(right, word[1])
        self.native_progress = True
        self.cancel_timer()
        self.position = left
        self.on_range(left, right)

    def completed(self, token):
        if not self.closed and self.state == "speaking" and token == self.token:
            self.index += 1
            self.next()

    def failed(self, token):
        if not self.closed and token == self.token:
            self.stop()
            self.on_state(
                "unavailable", "Offline speech failed. Choose another installed voice."
            )

    def pause(self):
        if self.state == "speaking":
            self.cancel_timer()
            self.elapsed = max(0, self.clock() - self.started_at)
            self.state = "paused"
            if getattr(self.engine, 'pause_utterance', lambda: False)():
                self.native_paused = True
                self.on_state("paused", "Paused · Resume continues from the current word.")
                return
            self.generation += 1
            self.token = str(self.generation)
            self.engine.stop()
            text, base, end = self.ranges[self.index]
            offset = len(
                self.text.encode("utf-16-le")[: self.position * 2].decode("utf-16-le")
            )
            stop = len(self.text.encode("utf-16-le")[: end * 2].decode("utf-16-le"))
            self.ranges[self.index] = (self.text[offset:stop], self.position, end)
            self.on_state("paused", "Paused · Resume continues from the current word.")

    def resume(self):
        if not self.closed and self.state == "paused" and self.can_speak():
            self.state = "speaking"
            if self.native_paused:
                self.native_paused = False
                self.started_at = self.clock() - self.elapsed
                self.engine.resume_utterance()
                self.on_state("speaking", "Reading aloud · current word highlighted")
                if not self.native_progress and not getattr(self.engine, 'native_word_events', False):
                    index = next((i for i, (start, _) in enumerate(self.utterance_words) if start >= self.position), 0)
                    self.estimated_word(self.token, index)
            else:
                self.next()

    def set_speed(self, speed):
        """Re-synthesize from the current word; native rates apply per utterance."""
        if self.closed or speed == getattr(self, "speed", None):
            return
        speaking = self.state == "speaking"
        if speaking:
            self.pause()
        self.speed = speed
        if self.native_paused:
            getattr(self.engine, 'set_speed', lambda speed: None)(speed)
        if speaking:
            self.resume()

    def skip(self, seconds):
        """Estimate a time jump from word rate; system synthesis has no seek API."""
        if (
            self.closed
            or self.state not in {"speaking", "paused"}
            or not self.words
            or not self.ranges
        ):
            return
        paused = self.state == "paused"
        elapsed = self.elapsed if paused else max(0, self.clock() - self.started_at)
        current = bisect_right(self.words, self.ranges[self.index][1]) - 1
        target = max(
            0,
            min(
                len(self.words) - 1,
                current + round((elapsed + seconds) * 3 * self.speed),
            ),
        )
        self.cancel_timer()
        self.generation += 1
        self.token = str(self.generation)
        # Retire pixels and callbacks before stopping the old native utterance.
        self.on_range(-1, -1)
        self.engine.stop()
        self.native_paused = False
        self.ranges = list(
            self.utterances(self.text, self.words[target], self.end, breaks=self.breaks)
        )
        self.index, self.elapsed = 0, 0
        if paused:
            text, base, _ = self.ranges[0]
            word = next(word_ranges(text, base), None)
            if word:
                self.on_range(*word)
            self.on_state("paused", "Paused · Resume reads from the new position.")
        else:
            self.next()

    def stop(self):
        self.cancel_timer()
        self.generation += 1
        self.token = str(self.generation)
        self.state = "stopped"
        self.native_paused = False
        self.engine.stop()
        self.ranges, self.index = [], 0
        self.text, self.words, self.breaks = "", [], ()
        self.spoken = None
        self.utterance_words = []
        self.elapsed = 0
        self.on_range(-1, -1)
        self.on_state("stopped", "Stopped")

    def dispose(self):
        if not self.closed:
            self.stop()
            self.closed = True
            self.engine.close()
            self.engine.completed = self.engine.failed = self.engine.progress = (
                self.engine.started
            ) = lambda *args: None
            self.on_range = self.on_state = lambda *args: None
            self.can_speak = lambda: False
            self.on_finished = lambda: None
