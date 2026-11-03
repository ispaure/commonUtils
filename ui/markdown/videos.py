"""Inline native video controls over reserved rich-text image positions."""
from pathlib import Path
from urllib.parse import urlsplit

from .. import pyside as qt

VIDEO_SUFFIXES = {'.mp4', '.m4v', '.mov', '.webm', '.mkv', '.avi', '.mpg', '.mpeg', '.ogv', '.wmv', '.m2ts'}


def video_target(target):
    try:
        return Path(urlsplit(target).path).suffix.lower() in VIDEO_SUFFIXES
    except ValueError:
        return False


class VideoCard(qt.QWidget):
    def __init__(self, parent, url, label):
        super().__init__(parent)
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.screen = QVideoWidget(self)
        self.player.setVideoOutput(self.screen)
        self.url = url
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.screen, 1)
        controls = qt.QHBoxLayout()
        self.play = qt.QPushButton('Play')
        self.play.setAccessibleName('Play ' + label)
        self.play.clicked.connect(self.toggle)
        self.seek = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.seek.setAccessibleName('Video position')
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.player.durationChanged.connect(lambda value: self.seek.setRange(0, min(value, 2147483647)))
        self.player.positionChanged.connect(lambda value: self.seek.setValue(value) if not self.seek.isSliderDown() else None)
        self.player.playbackStateChanged.connect(lambda state: self.play.setText('Pause' if state == QMediaPlayer.PlaybackState.PlayingState else 'Play'))
        self.status = qt.QLabel(label)
        self.player.errorOccurred.connect(lambda *_: self.status.setText(self.player.errorString()))
        controls.addWidget(self.play)
        controls.addWidget(self.seek, 1)
        layout.addLayout(controls)
        layout.addWidget(self.status)

    def toggle(self):
        if self.player.source().isEmpty():
            self.player.setSource(qt.QUrl(self.url))
        if self.player.isPlaying():
            self.player.pause()
        else:
            self.player.play()

    def retire(self):
        self.player.stop()
        self.player.setSource(qt.QUrl())
        self.hide()
        self.deleteLater()


class InlineVideos(qt.QObject):
    def __init__(self, widget, resolve):
        super().__init__(widget)
        self.widget, self.resolve, self.cards = widget, resolve, {}
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        widget.textChanged.connect(lambda: self.timer.start(0))
        widget.document().documentLayout().documentSizeChanged.connect(lambda *_: self.timer.start(0))
        widget.verticalScrollBar().valueChanged.connect(lambda *_: self.timer.start(0))
        widget.horizontalScrollBar().valueChanged.connect(lambda *_: self.timer.start(0))
        widget.installEventFilter(self)
        widget.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.Hide:
            for card in self.cards.values():
                card.player.pause()
        if event.type() in (qt.QEvent.Type.Show, qt.QEvent.Type.Resize):
            self.timer.start(0)
        return False

    def clear(self):
        for card in self.cards.values():
            card.retire()
        self.cards.clear()

    def refresh(self):
        from .images import ResponsiveImages
        document, wanted = self.widget.document(), {}
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                fmt = fragment.charFormat()
                if fmt.isImageFormat() and video_target(fmt.toImageFormat().name()):
                    image = fmt.toImageFormat()
                    target = document.baseUrl().resolved(qt.QUrl(image.name()))
                    source = self.resolve(target)
                    if source:
                        key = fragment.position(), str(source)
                        card = self.cards.get(key)
                        if card is None:
                            card = VideoCard(self.widget.viewport(), str(source), Path(target.toLocalFile()).name)
                        wanted[key] = card
                        cursor = qt.QTextCursor(document)
                        cursor.setPosition(fragment.position())
                        rect = self.widget.cursorRect(cursor)
                        size = ResponsiveImages().intrinsicSize(document, fragment.position(), fmt)
                        card.setGeometry(rect.x(), rect.y(), round(size.width()), round(size.height()))
                        card.setVisible(self.widget.isVisible())
                iterator += 1
            block = block.next()
        for key, card in self.cards.items():
            if key not in wanted:
                card.retire()
        self.cards = wanted
