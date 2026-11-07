"""Inline native video controls over reserved rich-text image positions."""
from pathlib import Path
from threading import Event
from urllib.parse import unquote, urlsplit

from .. import pyside as qt

VIDEO_SUFFIXES = {'.mp4', '.m4v', '.mov', '.webm', '.mkv', '.avi', '.mpg', '.mpeg', '.ogv', '.wmv', '.m2ts'}


def video_target(target):
    try:
        return (Path(target).suffix.lower() in VIDEO_SUFFIXES or
                Path(unquote(urlsplit(target).path)).suffix.lower() in VIDEO_SUFFIXES)
    except ValueError:
        return False


class VideoSurface(qt.QWidget):
    """Paint decoded frames consistently in native and offscreen text viewers."""
    def __init__(self, parent):
        super().__init__(parent)
        from PySide6.QtMultimedia import QVideoSink
        self.sink = QVideoSink(self)
        self.current_image = qt.QImage()
        self.sink.videoFrameChanged.connect(self.frame_changed)

    def videoSink(self):
        return self.sink

    def frame_changed(self, frame):
        self.current_image = frame.toImage() if frame.isValid() else qt.QImage()
        self.update()

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        try:
            painter.fillRect(self.rect(), qt.QColor('black'))
            if not self.current_image.isNull():
                size = self.current_image.size().scaled(self.size(), qt.Qt.AspectRatioMode.KeepAspectRatio)
                target = qt.QRect((self.width() - size.width()) // 2, (self.height() - size.height()) // 2,
                                  size.width(), size.height())
                painter.setRenderHint(qt.QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(target, self.current_image)
        finally:
            painter.end()


class VideoCard(qt.QWidget):
    source_ready = qt.Signal(object, str)

    def __init__(self, parent, url, label):
        super().__init__(parent)
        self.load_source = url if callable(url) else None
        self.url = '' if self.load_source is not None else url
        self.player = self.audio = self.screen = None
        self.pending = None
        self.source_ready.connect(self.publish_source, qt.Qt.ConnectionType.QueuedConnection)
        self.label = label
        self.setObjectName('markdownVideo')
        self.setAttribute(qt.Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet('''
            QWidget#markdownVideo { background: #151922; border: 1px solid #353c48; border-radius: 8px; }
            QWidget#markdownVideo QLabel { color: #edf1f7; }
            QWidget#markdownVideo QPushButton {
                color: #edf1f7; background: #303947; border: 1px solid #576579;
                border-radius: 5px; padding: 4px 12px;
            }
            QWidget#markdownVideo QPushButton:hover { background: #414d60; }
            QWidget#markdownVideo QPushButton:focus { border-color: #adcaff; }
        ''')
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        placeholder = qt.QLabel('Video')
        placeholder.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(placeholder, 1)
        controls = qt.QHBoxLayout()
        self.play = qt.QPushButton('Play')
        self.play.setAccessibleName('Play ' + label)
        # Mouse focus can make the text view scroll to its old cursor before
        # the release reaches this overlay. Keep both controls keyboard reachable.
        self.play.setFocusPolicy(qt.Qt.FocusPolicy.TabFocus)
        self.play.clicked.connect(self.toggle)
        self.seek = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.seek.setFocusPolicy(qt.Qt.FocusPolicy.TabFocus)
        self.seek.setAccessibleName('Video position')
        self.seek.setRange(0, 0)
        self.seek.setEnabled(False)
        self.status = qt.QLabel(label)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(0)
        controls.addWidget(self.play)
        controls.addWidget(self.seek, 1)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        if self.load_source is None:
            self.create_player()

    def create_player(self):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.screen = VideoSurface(self)
        self.player.setVideoSink(self.screen.videoSink())
        self.layout().takeAt(0).widget().deleteLater()
        self.layout().insertWidget(0, self.screen, 1)
        self.seek.valueChanged.connect(self.player.setPosition)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.seekableChanged.connect(lambda *_: self.update_seek())
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.errorOccurred.connect(lambda *_: self.status.setText(self.player.errorString()))

    def duration_changed(self, value):
        with qt.QSignalBlocker(self.seek):
            self.seek.setRange(0, max(0, min(value, 2147483647)))
        self.update_seek()

    def update_seek(self):
        self.seek.setEnabled(self.player.isSeekable() and self.seek.maximum() > 0)

    def position_changed(self, value):
        if not self.seek.isSliderDown():
            with qt.QSignalBlocker(self.seek):
                self.seek.setValue(value)

    def state_changed(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        label = 'Pause' if state == QMediaPlayer.PlaybackState.PlayingState else 'Play'
        self.play.setText(label)
        self.play.setAccessibleName(label + ' ' + self.label)

    def toggle(self):
        if self.player is not None and self.player.isPlaying():
            self.player.pause()
        elif self.load_source is not None:
            if self.pending is not None:
                return
            self.pending = stopped = Event()
            self.play.setText('Loading…')
            self.status.setText('Preparing video…')
            load, publish = self.load_source, self.source_ready.emit

            def work():
                try:
                    url = load(stopped.is_set) or ''
                except Exception:
                    url = ''
                try:
                    publish(stopped, url)
                except RuntimeError:
                    pass  # The widget can be destroyed while its worker retires.

            qt.QThreadPool.globalInstance().start(work)
        else:
            if self.player.source().isEmpty():
                self.player.setSource(qt.QUrl(self.url))
            self.player.play()

    @qt.Slot(object, str)
    def publish_source(self, stopped, url):
        if self.pending is not stopped:
            return
        self.pending = None
        self.play.setText('Play')
        self.status.setText(self.label if stopped.is_set() or url else 'Video unavailable.')
        if url and not stopped.is_set():
            if self.player is None:
                self.create_player()
            self.url = url
            source = qt.QUrl(url)
            if self.player.source() != source:
                self.player.setSource(source)
            self.player.play()

    def pause(self):
        if self.pending is not None:
            self.pending.set()
        if self.player is not None:
            self.player.pause()

    def retire(self):
        self.pause()
        if self.player is not None:
            from PySide6.QtMultimedia import QVideoFrame
            self.player.stop()
            self.player.setSource(qt.QUrl())
            self.screen.videoSink().setVideoFrame(QVideoFrame())
            self.screen.current_image = qt.QImage()
        self.hide()
        self.deleteLater()


class InlineVideos(qt.QObject):
    def __init__(self, widget, resolve):
        super().__init__(widget)
        self.widget, self.resolve, self.cards = widget, resolve, {}
        self.entries = None
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        widget.textChanged.connect(self.invalidate)
        widget.document().baseUrlChanged.connect(lambda *_: self.invalidate())
        widget.document().documentLayout().documentSizeChanged.connect(lambda *_: self.timer.start(0))
        widget.verticalScrollBar().valueChanged.connect(lambda *_: self.timer.start(0))
        widget.horizontalScrollBar().valueChanged.connect(lambda *_: self.timer.start(0))
        widget.installEventFilter(self)
        widget.viewport().installEventFilter(self)

    def invalidate(self):
        self.entries = None
        self.timer.start(0)

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.Hide:
            for card in self.cards.values():
                card.pause()
        if event.type() in (qt.QEvent.Type.Show, qt.QEvent.Type.Resize):
            self.timer.start(0)
        return False

    def clear(self):
        self.timer.stop()
        self.entries = []
        for card in self.cards.values():
            card.retire()
        self.cards.clear()

    def refresh(self):
        from .images import ResponsiveImages
        document, wanted = self.widget.document(), {}
        if self.entries is None:
            self.entries = []
            block = document.begin()
            while block.isValid():
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat() and video_target(fmt.toImageFormat().name()):
                        self.entries.append((fragment.position(), fmt))
                    iterator += 1
                block = block.next()
        for position, fmt in self.entries:
            target = document.baseUrl().resolved(qt.QUrl(fmt.toImageFormat().name()))
            source = self.resolve(target)
            if not source:
                continue
            source = source if callable(source) else str(source)
            key = position, source
            card = self.cards.get(key)
            if card is None:
                card = VideoCard(self.widget.viewport(), source, Path(target.toLocalFile()).name)
            wanted[key] = card
            cursor = qt.QTextCursor(document)
            cursor.setPosition(position)
            rect = self.widget.cursorRect(cursor)
            size = ResponsiveImages().intrinsicSize(document, position, fmt)
            card.setGeometry(rect.x(), rect.y(), round(size.width()), round(size.height()))
            card.setVisible(self.widget.isVisible())
        for key, card in self.cards.items():
            if key not in wanted:
                card.retire()
        self.cards = wanted
