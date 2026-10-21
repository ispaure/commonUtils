"""Local image drops and animated document resources for Qt Markdown surfaces."""
import os
from pathlib import Path
from urllib.parse import quote

from .. import pyside as qt
from ...filesystem.local_access import check_local_path


class ImageDropMixin:
    """Insert references without copying files or Qt's transient clipboard images."""
    image_base = None
    local_image_drops = True

    def _image_urls(self, source):
        if not self.local_image_drops or not source.hasUrls():
            return []
        urls = source.urls()
        for url in urls:
            if not url.isLocalFile():
                return []
            try:
                check_local_path(url.toLocalFile())
                if not qt.QImageReader(url.toLocalFile()).canRead():
                    return []
            except (OSError, ValueError):
                return []
        return urls

    def canInsertFromMimeData(self, source):
        return bool(self._image_urls(source)) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        urls = self._image_urls(source)
        if self.isReadOnly():
            return
        if not urls:
            return super().insertFromMimeData(source)
        base = self.image_base() if self.image_base else None
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for index, url in enumerate(urls):
            path = Path(url.toLocalFile()).absolute()
            target = url.toString(qt.QUrl.ComponentFormattingOption.FullyEncoded)
            if base is not None:
                try:
                    target = quote(Path(os.path.relpath(path.resolve(), Path(base).resolve())).as_posix(), safe='/')
                except ValueError:  # Separate Windows drives require an absolute URL.
                    pass
            if index:
                cursor.insertBlock()
            if isinstance(self, qt.QPlainTextEdit):
                label = path.stem.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
                cursor.insertText(f'![{label}]({target})')
            else:
                fmt = qt.QTextImageFormat()
                fmt.setName(target)
                fmt.setProperty(qt.QTextFormat.Property.ImageAltText, path.stem)
                cursor.insertImage(fmt)
        cursor.endEditBlock()
        self.setTextCursor(cursor)


class AnimatedImages(qt.QObject):
    """Retain one decoder per local GIF and repaint without editing source/history."""
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.movies = {}
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        widget.textChanged.connect(lambda: self.timer.start(0))
        widget.document().baseUrlChanged.connect(lambda url: self.timer.start(0))
        widget.installEventFilter(self)

    def refresh(self):
        document = self.widget.document()
        wanted = {}
        # Provider resources must stay behind their loader's access boundary.
        provider = getattr(self.widget, 'resource_loader', None) or getattr(document, 'resource_loader', None)
        if provider is None:
            block = document.begin()
            while block.isValid():
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    if fragment.charFormat().isImageFormat():
                        name = fragment.charFormat().toImageFormat().name()
                        url = document.baseUrl().resolved(qt.QUrl(name))
                        if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == '.gif':
                            wanted[name] = url.toLocalFile()
                    iterator += 1
                block = block.next()
        for name, (path, movie) in list(self.movies.items()):
            if wanted.get(name) != path:
                movie.stop()
                movie.deleteLater()
                del self.movies[name]
        for name, path in wanted.items():
            if name in self.movies:
                continue
            try:
                check_local_path(path)
            except (OSError, ValueError):
                continue
            movie = qt.QMovie(path, qt.QByteArray(), self)
            if not movie.isValid():
                movie.deleteLater()
                continue
            self.movies[name] = (path, movie)
            movie.frameChanged.connect(lambda frame, name=name, movie=movie: self._frame(name, movie))
            movie.start()
            if not self.widget.isVisible():
                movie.setPaused(True)

    def _frame(self, name, movie):
        document = self.widget.document()
        url = document.baseUrl().resolved(qt.QUrl(name))
        document.addResource(qt.QTextDocument.ResourceType.ImageResource, url, movie.currentImage())
        document.markContentsDirty(0, document.characterCount())
        self.widget.viewport().update()

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Show, qt.QEvent.Type.Hide):
            for _, movie in self.movies.values():
                movie.setPaused(event.type() == qt.QEvent.Type.Hide)
        return False
