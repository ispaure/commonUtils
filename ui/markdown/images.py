"""Local image drops and animated document resources for Qt Markdown surfaces."""
import os
import re
from pathlib import Path
from urllib.parse import quote

from .. import pyside as qt
from ...filesystem.local_access import check_local_path
from ...formats.markdown.images import image_size
from .syntax import FENCE_OPEN, fence_close


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
                responsive_image_format(fmt)
                cursor.insertImage(fmt)
        cursor.endEditBlock()
        self.setTextCursor(cursor)


class AnimatedImages(qt.QObject):
    """Retain one decoder per local GIF and repaint without editing source/history."""
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.handler = ResponsiveImages(self)
        widget.document().documentLayout().registerHandler(qt.QTextFormat.ObjectTypes.ImageObject, self.handler)
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
            if not movie.isValid() or not movie.jumpToFrame(0) or movie.currentImage().isNull():
                movie.deleteLater()
                continue
            self.movies[name] = (path, movie)
            movie.frameChanged.connect(lambda frame, name=name, movie=movie: self._frame(name, movie))
            movie.error.connect(lambda error, name=name, movie=movie: self._failed_movie(name, movie))
            movie.start()
            if not self.widget.isVisible():
                movie.setPaused(True)

    def _failed_movie(self, name, movie):
        if name in self.movies and self.movies[name][1] is movie:
            del self.movies[name]
            movie.stop()
            movie.deleteLater()

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


WIKI_IMAGE_SOURCE = int(qt.QTextFormat.Property.UserProperty) + 703
_WIKI_IMAGE = re.compile(r'(?<![\\!])!\[\[([^]\n|]+)(?:\|([^]\n]+))?\]\]')
_CODE = re.compile(r'(?<!`)(`+)(?!`)(.*?)\1(?!`)')


def prepare_wiki_images(markdown):
    """Translate image embeds for Qt, retaining their exact spelling for export."""
    prefix = 'zzwikiimage'
    while prefix in markdown:
        prefix += 'z'
    tokens, lines, fence = {}, [], None
    for line in markdown.splitlines(keepends=True):
        content = re.sub(r'^(?: {0,3}>[ \t]?)+', '', line).rstrip('\r\n')
        opening = FENCE_OPEN.fullmatch(content)
        if fence:
            lines.append(line)
            if fence_close(content, fence):
                fence = None
            continue
        if opening:
            fence = opening[1]
            lines.append(line)
            continue
        if line.startswith(('    ', '\t')):
            lines.append(line)
            continue
        code = [(match.start(), match.end()) for match in _CODE.finditer(line)]
        def replace(match):
            if any(start <= match.start() < end for start, end in code):
                return match[0]
            target = match[1].strip()
            if Path(target).suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico', '.tif', '.tiff'):
                return match[0]
            key = f'{prefix}{len(tokens)}z'
            suffix = match[2] or ''
            alt = target + '|' + suffix if image_size(suffix)[1] is not None else (suffix or target)
            tokens[key] = (match[0], alt)
            return f'![{key}]({quote(target, safe="/:%")})'
        lines.append(_WIKI_IMAGE.sub(replace, line))
    return ''.join(lines), tokens


def responsive_image_format(fmt):
    """Qt's native percentage cap reflows images without editing on resize."""
    fmt.setProperty(qt.QTextFormat.Property.ImageMaxWidth,
                    qt.QTextLength(qt.QTextLength.Type.PercentageLength, 100))
    _, width, height = image_size(fmt.property(qt.QTextFormat.Property.ImageAltText) or '')
    if width is not None:
        fmt.setWidth(width)
        if height is not None:
            fmt.setHeight(height)
    return fmt


def configure_images(document, tokens=None):
    tokens = tokens or {}
    block = document.begin()
    changes = []
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.charFormat().isImageFormat():
                fmt = fragment.charFormat().toImageFormat()
                original = tokens.get(fmt.property(qt.QTextFormat.Property.ImageAltText))
                if original:
                    fmt.setProperty(WIKI_IMAGE_SOURCE, original[0])
                    fmt.setProperty(qt.QTextFormat.Property.ImageAltText, original[1])
                changes.append((fragment.position(), fragment.length(), responsive_image_format(fmt)))
            iterator += 1
        block = block.next()
    for position, length, fmt in changes:
        cursor = qt.QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, qt.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)


class ResponsiveImages(qt.QPyTextObject):
    """Keep the requested aspect ratio when a fixed-size image exceeds its page."""
    @staticmethod
    def _image(document, fmt):
        url = document.baseUrl().resolved(qt.QUrl(fmt.toImageFormat().name()))
        image = document.resource(qt.QTextDocument.ResourceType.ImageResource, url)
        if isinstance(image, qt.QPixmap):
            image = image.toImage()
        return image if isinstance(image, qt.QImage) else qt.QImage()

    def intrinsicSize(self, document, position, fmt):
        image = self._image(document, fmt)
        image_format = fmt.toImageFormat()
        natural = image.deviceIndependentSize()
        width = image_format.width() or natural.width() or 16
        height = image_format.height() or (width * natural.height() / natural.width() if natural.width() else 16)
        block = document.findBlock(position).blockFormat()
        frame = document.rootFrame().frameFormat()
        available = (document.textWidth() - frame.leftMargin() - frame.rightMargin()
                     - block.leftMargin() - block.rightMargin() - block.indent() * document.indentWidth())
        if available > 0 and width > available:
            height *= available / width
            width = available
        return qt.QSizeF(width, height)

    def drawObject(self, painter, rect, document, position, fmt):
        image = self._image(document, fmt)
        if not image.isNull():
            painter.drawImage(rect, image)
        else:
            painter.save()
            painter.setPen(qt.QColor('gray'))
            painter.drawRect(rect.adjusted(.5, .5, -.5, -.5))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.restore()
