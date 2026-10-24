"""Platform speech adapters. Only installed, offline voices are offered."""

import weakref

_delegate_class = None


def _android_listeners(speech):
    from android.speech.tts import TextToSpeech
    from java import dynamic_proxy

    owner = weakref.ref(speech)

    class Init(dynamic_proxy(TextToSpeech.OnInitListener)):
        def onInit(self, status):
            engine = owner()
            if engine is not None:
                engine.loop.call_soon_threadsafe(engine.initialized, status)

    from io.github.ispaure.commonutils import SpeechListener

    class Complete(dynamic_proxy(SpeechListener.Listener)):
        def started(self, token):
            engine = owner()
            if engine is not None:
                engine.begin(str(token))

        def progress(self, token, start, end):
            engine = owner()
            if engine is not None:
                engine.word_range(str(token), int(start), int(end))

        def completed(self, token):
            engine = owner()
            if engine is not None:
                engine.deliver(str(token))

        def failed(self, token):
            engine = owner()
            if engine is not None:
                engine.failure(str(token))

    return Complete(), Init()


def _apple_delegate_class():
    global _delegate_class
    import ctypes

    ctypes.CDLL("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")
    from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property
    from rubicon.objc.types import NSRange

    if _delegate_class is None:

        class CommonUtilsSpeechDelegate(
            ObjCClass("NSObject"),
            protocols=(ObjCProtocol("AVSpeechSynthesizerDelegate"),),
        ):
            owner = objc_property(object, weak=True)

            @objc_method
            def speechSynthesizer_didStartSpeechUtterance_(
                self, synth, utterance
            ) -> None:
                engine = self.owner
                if (
                    engine is not None
                    and getattr(engine, "utterance", None) is not None
                ):
                    if utterance.ptr.value == engine.utterance.ptr.value:
                        engine.begin(engine.token)

            @objc_method
            def speechSynthesizer_willSpeakRangeOfSpeechString_utterance_(
                self, synth, characterRange: NSRange, utterance
            ) -> None:
                engine = self.owner
                if (
                    engine is not None
                    and getattr(engine, "utterance", None) is not None
                ):
                    if utterance.ptr.value == engine.utterance.ptr.value:
                        engine.word_range(
                            engine.token,
                            int(characterRange.location),
                            int(characterRange.location + characterRange.length),
                        )

            @objc_method
            def speechSynthesizer_didFinishSpeechUtterance_(
                self, synth, utterance
            ) -> None:
                engine = self.owner
                if (
                    engine is not None
                    and getattr(engine, "utterance", None) is not None
                ):
                    if utterance.ptr.value == engine.utterance.ptr.value:
                        engine.deliver(engine.token)

            @objc_method
            def speechSynthesizer_didCancelSpeechUtterance_(
                self, synth, utterance
            ) -> None:
                engine = self.owner
                if (
                    engine is not None
                    and getattr(engine, "utterance", None) is not None
                ):
                    if utterance.ptr.value == engine.utterance.ptr.value:
                        engine.failure(engine.token)

        _delegate_class = CommonUtilsSpeechDelegate
    return _delegate_class


class NativeSpeech:
    def __init__(self, loop):
        self.loop, self.ready, self.error, self.closed = loop, False, "", False
        self.voices, self.completed = {}, lambda *args: None
        self.failed = self.progress = self.started = lambda *args: None
        self.default_voice = ""
        from toga.platform import get_factory

        backend = get_factory().WebView.__module__
        self.backend = backend
        try:
            if backend.startswith("toga_android."):
                self.android()
            elif backend.startswith("toga_iOS."):
                self.apple()
            else:
                self.error = "Read-aloud requires an Android or iOS speech engine."
        except ImportError:
            self.error = "Speech support is missing from this build. Update the app."
        except Exception:
            self.error = "Speech engine unavailable. Install an offline system voice."

    def deliver(self, token):
        if not self.closed:
            self.loop.call_soon_threadsafe(
                lambda: None if self.closed else self.completed(token)
            )

    def failure(self, token):
        if not self.closed:
            self.loop.call_soon_threadsafe(
                lambda: None if self.closed else self.failed(token)
            )

    def word_range(self, token, start, end):
        if not self.closed:
            self.loop.call_soon_threadsafe(
                lambda: None if self.closed else self.progress(token, start, end)
            )

    def begin(self, token):
        if not self.closed:
            self.loop.call_soon_threadsafe(
                lambda: None if self.closed else self.started(token)
            )

    def android(self):
        from android.speech.tts import TextToSpeech
        from org.beeware.android import MainActivity
        from io.github.ispaure.commonutils import SpeechListener

        self.listener, self.init_listener = _android_listeners(self)
        self.progress_listener = SpeechListener(self.listener)
        self.native = TextToSpeech(MainActivity.singletonThis, self.init_listener)

    def initialized(self, status):
        try:
            self.load_android_voices(status)
        except Exception:
            self.ready = False
            self.error = (
                "Offline voices could not be loaded. Check system speech settings."
            )

    def load_android_voices(self, status):
        if self.closed:
            return
        if status != 0:
            self.error = "Speech engine unavailable. Install an offline system voice."
            return
        from android.media import AudioAttributes

        self.native.setAudioAttributes(
            AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
        )
        self.native.setOnUtteranceProgressListener(self.progress_listener)

        def offer(voice):
            if voice is None:
                return
            try:
                features = voice.getFeatures()
                features = (
                    {str(v) for v in features.toArray()}
                    if features is not None
                    else set()
                )
                if (
                    not voice.isNetworkConnectionRequired()
                    and "notInstalled" not in features
                ):
                    label = (
                        str(voice.getLocale().toLanguageTag())
                        + " · "
                        + str(voice.getName())
                    )
                    self.voices[label] = voice
                    return label
            except Exception:
                # One malformed engine entry must not hide other usable voices.
                return

        try:
            voices = self.native.getVoices()
            if voices is not None:
                for voice in voices.toArray():
                    offer(voice)
        except Exception:
            pass
        # Also ask for the selected/default voice: an engine's enumeration may
        # be empty or incomplete. Apply the same offline/install checks to both.
        defaults = []
        for getter in (self.native.getVoice, self.native.getDefaultVoice):
            try:
                candidate = getter()
                label = offer(candidate)
                if label is not None:
                    defaults.append(label)
            except Exception:
                pass
        self.default_voice = next(
            iter(defaults),
            next(
                (label for label in self.voices if label.startswith("en-US")),
                next(iter(self.voices), ""),
            ),
        )
        self.ready = bool(self.voices)
        if not self.ready:
            self.error = (
                "No offline voice available. In phone Settings, search for Text-to-speech, "
                "select an engine and install voice data for your language. Then reopen Read aloud."
            )

    def apple(self):
        self.native_word_events = True
        delegate_class = _apple_delegate_class()
        from rubicon.objc import ObjCClass

        self.native = ObjCClass("AVSpeechSynthesizer").alloc().init()
        self.native.usesApplicationAudioSession = True
        self.delegate = delegate_class.alloc().init()
        self.delegate.owner = self
        self.native.delegate = self.delegate
        self.utterance = None
        voices = ObjCClass("AVSpeechSynthesisVoice").speechVoices
        for voice in voices() if callable(voices) else voices:
            self.voices[str(voice.language) + " · " + str(voice.name)] = voice
        default = ObjCClass("AVSpeechSynthesisVoice").voiceWithLanguage(None)
        self.default_voice = next(
            (
                label
                for label, voice in self.voices.items()
                if default is not None
                and str(voice.identifier) == str(default.identifier)
            ),
            next(iter(self.voices), ""),
        )
        self.ready = bool(self.voices)
        if not self.ready:
            self.error = (
                "No installed voice. Add a system voice in Spoken Content settings."
            )

    def voice_for_language(self, language, preferred=''):
        from ...runtime.speech_language import matching_locale
        fallback = preferred if preferred in self.voices else self.default_voice
        locales = {label: label.split(' · ', 1)[0] for label in self.voices}
        tag = matching_locale(language, locales.values(), locales.get(fallback, ''))
        if not language:
            return fallback
        if fallback in locales and locales[fallback] == tag:
            return fallback
        return next((label for label in self.voices if locales[label] == tag), '')

    def speak(self, text, voice, speed, token):
        if self.closed or not self.ready or voice not in self.voices:
            raise RuntimeError("An installed offline voice is required.")
        self.token = token
        if self.backend.startswith("toga_android."):
            if (
                self.native.setVoice(self.voices[voice]) != 0
                or self.native.setSpeechRate(speed) != 0
            ):
                raise RuntimeError("Voice unavailable.")
            if self.native.speak(text, 0, None, token) != 0:
                raise RuntimeError("Speech engine failed.")
        else:
            from rubicon.objc import ObjCClass

            utterance = ObjCClass("AVSpeechUtterance").speechUtteranceWithString(text)
            utterance.voice = self.voices[voice]
            utterance.rate = min(1.0, max(0.1, 0.5 * speed))
            self.utterance = utterance
            self.native.speakUtterance(utterance)

    def stop(self):
        if getattr(self, "native", None) is not None:
            if self.backend.startswith("toga_android."):
                self.native.stop()
            else:
                self.utterance = None
                self.native.stopSpeakingAtBoundary(0)

    def close(self):
        if not self.closed:
            self.closed = True
            self.ready = False
            self.voices = {}
            # Retire presentation owners even if a native shutdown raises.
            self.completed = self.failed = self.progress = self.started = lambda *args: None
            self.stop()
            if getattr(self, "native", None) is not None:
                if self.backend.startswith("toga_android."):
                    self.progress_listener.detach()
                    self.native.shutdown()
                else:
                    self.native.delegate = None
