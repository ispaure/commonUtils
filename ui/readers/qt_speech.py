"""Qt-safe scheduling and installed-engine adapter for the portable speech session."""
from .. import pyside as qt


class QtScheduler:
    def __init__(self, parent):
        self.parent = parent

    def call_later(self, delay, callback, *args):
        timer = qt.QTimer(self.parent)
        timer.setSingleShot(True)
        def invoke():
            timer.deleteLater()
            callback(*args)
        timer.timeout.connect(invoke)
        timer.start(max(0, round(delay * 1000)))
        class Handle:
            def cancel(self):
                timer.stop()
                timer.deleteLater()
        return Handle()


class QtSpeechEngine:
    sentence_breaks = False

    def __init__(self, engine, speech_type, scheduler):
        self.engine, self.speech_type, self.loop = engine, speech_type, scheduler
        self.completed = self.failed = self.progress = self.started = lambda *args: None
        self.token = None
        self.paused = False
        engine.stateChanged.connect(self._state)
        engine.errorOccurred.connect(lambda *args: self.failed(self.token) if self.token else None)
        if hasattr(engine, 'sayingWord'):
            engine.sayingWord.connect(self._word)

    @property
    def ready(self):
        return self.engine.state() != self.speech_type.State.Error

    @property
    def error(self):
        return self.engine.errorString()

    @property
    def native_word_events(self):
        return bool(self.engine.engineCapabilities() & self.speech_type.Capability.WordByWordProgress)

    @property
    def utterance_limit(self):
        return 3000 if self.native_word_events else 350

    def set_speed(self, speed):
        percent = speed * 100
        self.engine.setRate((percent - 100) / (100 if percent >= 100 else 50))

    def speak(self, text, voice, speed, token):
        self.token, self.paused = token, False
        self.set_speed(speed)
        self.engine.say(text)

    def _state(self, state):
        token = self.token
        if token is None or state != self.engine.state():
            return
        if state == self.speech_type.State.Speaking:
            if not self.paused:
                self.started(token)
        elif state == self.speech_type.State.Ready:
            self.token = None
            # Never start the next utterance inside the native state callback.
            self.loop.call_later(0, self.completed, token)
        elif state == self.speech_type.State.Error:
            self.failed(token)

    def _word(self, word, utterance, start, length):
        if self.token is not None:
            self.progress(self.token, start, start + length)

    def pause_utterance(self):
        if self.token is None or not self.engine.engineCapabilities() & self.speech_type.Capability.PauseResume:
            return False
        self.paused = True
        self.engine.pause()
        return True

    def resume_utterance(self):
        self.engine.resume()
        self.paused = False

    def stop(self):
        self.token = None
        self.paused = False
        self.engine.stop()

    def close(self):
        self.stop()
