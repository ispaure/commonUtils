"""Cached storage charts embedded in the browser's navigation and selection flow."""
from pathlib import Path
import math
from bisect import bisect_right
from .. import pyside as qt
from ..operations import Operation
from ...directory_index import directory_cache
from ...filesystem import format_size
from ...settings import get_setting
from .storage import Treemap


class RadialMap(Treemap):
    parent_requested = qt.Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes = {}
        self.totals = {}
        self.root = None
        self.sectors = []
        self._scene = None
        self._scene_key = None
        self._scene_revision = 0
        self._hit_rings = {}
        from ..cursor_tooltip import CursorTooltip
        self.hover = CursorTooltip(self)
        self._zoom = 1.0
        self._zoom_start = 1.0
        self._animation = qt.QVariantAnimation(self)
        self._animation.setDuration(240)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(qt.QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._zoom_frame)
        self.setAccessibleName('Radial storage distribution; rings represent nested folders')

    def animate_navigation(self, direction):
        self._animation.stop()
        self._zoom = 1.0
        if (direction and self.isVisible() and
                get_setting('Storage', 'radial_animations_bool', True)):
            self._zoom_start = .78 if direction > 0 else 1.22
            self._zoom = self._zoom_start
            self._animation.start()
        self.update()

    def _zoom_frame(self, progress):
        self._zoom = self._zoom_start + (1.0-self._zoom_start)*progress
        self.update()

    def hideEvent(self, event):
        self._animation.stop()
        self._zoom = 1.0
        super().hideEvent(event)

    def set_items(self, items):
        self._scene_revision += 1
        self.sectors = []
        self.hover.hide()
        super().set_items(items)

    def _build_scene(self):
        ratio = self.devicePixelRatioF()
        self._scene = qt.QPixmap(max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio)))
        self._scene.setDevicePixelRatio(ratio)
        painter = qt.QPainter(self._scene)
        painter.setFont(self.font())
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().brush(qt.QPalette.ColorRole.Base))
        center = qt.QPointF(self.width()/2, self.height()/2)
        radius = max(0, min(self.width(), self.height())/2-12)
        ring = radius/5
        self.sectors = []
        self._hit_rings = {}
        def draw(parent, start, span, depth, hue=0):
            children = self.nodes.get(parent, [])
            total = self.totals.get(parent, sum(size for _, size in children))
            if not total or depth > 4:
                return
            angle = start
            for index, (path, size) in enumerate(children):
                sweep = span*size/total
                if sweep <= 0:
                    continue
                outer, inner = ring*(depth+1), ring*depth
                bounds = qt.QRectF(center.x()-outer, center.y()-outer, outer*2, outer*2)
                inside = qt.QRectF(center.x()-inner, center.y()-inner, inner*2, inner*2)
                shape = qt.QPainterPath()
                shape.arcMoveTo(bounds, angle); shape.arcTo(bounds, angle, sweep)
                radians = math.radians(angle+sweep)
                shape.lineTo(center.x()+inner*math.cos(radians), center.y()-inner*math.sin(radians))
                shape.arcTo(inside, angle+sweep, -sweep); shape.closeSubpath()
                color = (index*47)%360 if depth == 1 else hue
                painter.setPen(qt.QPen(self.palette().color(qt.QPalette.ColorRole.Base), 1))
                painter.setBrush(qt.QColor.fromHsv(color, 150-depth*15, 155+depth*15))
                painter.drawPath(shape)
                self.sectors.append((path, size, shape))
                self._hit_rings.setdefault(depth, []).append((angle, angle + sweep, path, size))
                draw(path, angle, sweep, depth+1, color)
                angle += sweep
        draw(self.root, 0, 360, 1)
        painter.setPen(self.palette().color(qt.QPalette.ColorRole.Text))
        painter.drawText(qt.QRectF(center.x()-ring, center.y()-ring, ring*2, ring*2),
                         qt.Qt.AlignmentFlag.AlignCenter, format_size(sum(size for _,size in self.items)))
        if not self.sectors:
            painter.drawText(self.rect(), qt.Qt.AlignmentFlag.AlignCenter, 'No file bytes to display')
        painter.end()
        self._sector_paths = {path: shape for path, size, shape in self.sectors}
        self._hit_starts = {depth: [entry[0] for entry in entries] for depth, entries in self._hit_rings.items()}

    def _ensure_scene(self):
        key = (self.size(), self.devicePixelRatioF(), self._scene_revision,
               self.palette().cacheKey(), self.font().toString())
        if key != self._scene_key:
            self._build_scene()
            self._scene_key = key

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(qt.QPalette.ColorRole.Base))
        if self.loading:
            return
        self._ensure_scene()
        center = qt.QPointF(self.width() / 2, self.height() / 2)
        painter.translate(center)
        painter.scale(self._zoom, self._zoom)
        painter.translate(-center)
        painter.drawPixmap(0, 0, self._scene)
        selected = self._sector_paths.get(self.selected_path)
        if selected is not None:
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.setPen(qt.QPen(self.palette().color(qt.QPalette.ColorRole.Highlight), 3))
            painter.setBrush(qt.Qt.BrushStyle.NoBrush)
            painter.drawPath(selected)

    def _in_center(self, point):
        radius = max(0, min(self.width(), self.height()) / 2 - 12) / 5 * self._zoom
        return ((point.x() - self.width() / 2) ** 2 +
                (point.y() - self.height() / 2) ** 2 <= radius ** 2)

    def mouseMoveEvent(self, event):
        if self.loading:
            self.hover.hide()
            return
        item = self.hit(event.position())
        text = f'{item[0]}\n{format_size(item[1])}' if item else ''
        if self.root is not None and self._in_center(event.position()):
            text = 'Double-click to go up one folder'
        self.hover.show(text, event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event):
        if (self.root is not None and event.button() == qt.Qt.MouseButton.LeftButton
                and self._in_center(event.position())):
            self.parent_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def hit(self, point):
        if self.loading:
            return None
        self._ensure_scene()
        ring = max(0, min(self.width(), self.height()) / 2 - 12) / 5
        if not ring:
            return None
        dx = (point.x() - self.width() / 2) / self._zoom
        dy = (point.y() - self.height() / 2) / self._zoom
        depth = int(math.hypot(dx, dy) / ring)
        entries = self._hit_rings.get(depth, ())
        if not entries:
            return None
        angle = math.degrees(math.atan2(-dy, dx)) % 360
        index = bisect_right(self._hit_starts[depth], angle) - 1
        if index >= 0:
            start, end, path, size = entries[index]
            if start <= angle <= end:
                return path, size
        return None


class StorageView(qt.QWidget):
    selection_changed = qt.Signal()
    activated = qt.Signal(object)
    idle = qt.Signal()
    context_requested = qt.Signal(object, object)

    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.root = None
        self.selected_path = None
        self.busy = False
        self.closing = False
        self.pending = False
        self._revision = 0
        self._loaded_key = None
        self._request_key = None
        self._last_result = None
        self._results_cache = {}
        self._navigation_zoom = 0
        self.entries = []
        self.nodes = {}
        self._rows = {}
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        controls = qt.QHBoxLayout()
        self.chart_selector = qt.QComboBox()
        self.chart_selector.addItems(['Treemap', 'Radial'])
        self.chart_selector.setAccessibleName('Storage visualization')
        self.chart_selector.setToolTip('Treemap shows this folder; Radial shows up to four levels and 3,000 chart entries shared across branches. Gaps can represent omitted entries or incomplete sizes; zero-byte folders have no area. Hover for names and sizes.')
        self.chart_selector.hide()  # Compatibility API; the toolbar owns chart buttons.
        self.summary = qt.QLabel('')
        self.summary.setWordWrap(True)
        controls.addWidget(self.summary,1)
        layout.addLayout(controls)
        self.charts = qt.QStackedWidget()
        self.map = Treemap()
        self.radial = RadialMap()
        self.radial.parent_requested.connect(self.browser.navigation.up.click)
        for chart in (self.map,self.radial):
            self.charts.addWidget(chart)
            chart.selected.connect(self.select_path)
            chart.activated.connect(self.activated)
            chart.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
            chart.customContextMenuRequested.connect(lambda point, target=chart: self._chart_context(target,point))
        self.chart_selector.currentIndexChanged.connect(self._chart_changed)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['File or folder', 'Size', 'Share'])
        self.results.headerItem().setToolTip(0, 'Files and folders, ordered largest first')
        self.results.setRootIsDecorated(True)
        self.results.setUniformRowHeights(True)
        self.results.header().setSectionResizeMode(0,qt.QHeaderView.ResizeMode.Stretch)
        for column in (1,2):
            self.results.header().setSectionResizeMode(column,qt.QHeaderView.ResizeMode.ResizeToContents)
        self.results.currentItemChanged.connect(lambda row, old: self._selected(row))
        self.results.itemActivated.connect(lambda row, column: self.activated.emit(row.data(0,qt.Qt.ItemDataRole.UserRole)))
        self.results.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self._list_context)
        self.splitter = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.results.setMinimumWidth(220)
        self.splitter.addWidget(self.charts); self.splitter.addWidget(self.results)
        self.splitter.setStretchFactor(0,7); self.splitter.setStretchFactor(1,3)
        self.splitter.setSizes([700,300]); layout.addWidget(self.splitter,1)
        browser.index_updated.connect(self._index_changed)

    def _index_changed(self, path):
        if path == self.root:
            self._revision += 1
            self.refresh()

    def _chart_changed(self, index):
        self.charts.setCurrentIndex(index)
        if self.browser.views.currentIndex() == 3:
            blocker = qt.QSignalBlocker(self.browser.view_selector)
            self.browser.view_selector.setCurrentIndex(3 + index)
            blocker.unblock()
        self.refresh()

    def _selected(self, row):
        self.selected_path = row.data(0,qt.Qt.ItemDataRole.UserRole) if row else None
        self._highlight()
        self.selection_changed.emit()

    def _highlight(self):
        for chart in (self.map,self.radial):
            chart.selected_path = self.selected_path
            chart.update()

    def select_path(self, path):
        self.selected_path = Path(path)
        blocker = qt.QSignalBlocker(self.results)
        self.results.clearSelection()
        item = self._rows.get(self.selected_path)
        if item is not None:
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self.results.setCurrentItem(item)
            self.results.scrollToItem(item)
        blocker.unblock()
        self._highlight()
        self.selection_changed.emit()

    def _chart_context(self, chart, point):
        item = chart.hit(qt.QPointF(point))
        if item:
            self.select_path(item[0]); self.context_requested.emit(item[0],chart.mapToGlobal(point))

    def _list_context(self, point):
        item = self.results.itemAt(point)
        if item:
            self.select_path(item.data(0,qt.Qt.ItemDataRole.UserRole))
            self.context_requested.emit(self.selected_path,self.results.viewport().mapToGlobal(point))

    def _set_loading(self, loading):
        for chart in (self.map, self.radial):
            chart.loading = loading
            if loading and hasattr(chart, "hover"):
                chart.hover.hide()
            chart.update()

    def set_root(self, path):
        path = Path(path)
        if path != self.root:
            if self.busy:
                self.operation.requestInterruption()
            self._loaded_key = None
            self._last_result = None
            previous = self.root
            self._navigation_zoom = (1 if previous is not None and previous in path.parents else
                                     -1 if previous is not None and path in previous.parents else 0)
            self.radial.animate_navigation(0)
            self.root = path; self.selected_path = None
            self.results.clear(); self._rows = {}; self.map.set_items([])
            self.radial.nodes = {}; self.radial.set_items([])
            self.summary.clear()
            self._set_loading(True)
        self.refresh()

    def refresh(self):
        if self.closing or self.browser.views.currentIndex() != 3 or self.root is None:
            return
        key = (self.root, self.chart_selector.currentIndex(), self._revision)
        if key == self._loaded_key or self.busy and key == self._request_key:
            return
        if self.busy:
            self.pending = True
            self.operation.requestInterruption()
            return
        if key in self._results_cache:
            self._loaded(self.root, self._results_cache[key], '', key=key)
            return
        self._set_loading(True)
        self._request_key = key
        self.busy = True
        root = self.root
        radial = self.chart_selector.currentIndex() == 1
        operation = Operation(lambda: self._collect(root, radial=radial, cancelled=operation.isInterruptionRequested), self)
        self.operation = operation
        self.operation.completed.connect(lambda result,error: self._loaded(root,result,error, key=key))
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _collect(self, root, *, radial=False, cancelled=None):
        from .storage_data import collect_storage
        return collect_storage(directory_cache, root, radial=radial,
                               cancelled=cancelled or self.operation.isInterruptionRequested)

    def _loaded(self, root, result, error, *, key=None):
        if self.closing or root != self.root: return
        if key is not None and key != (self.root, self.chart_selector.currentIndex(), self._revision):
            return
        self._set_loading(False)
        if error:
            self.summary.setText(f'Saved sizes unavailable: {error}'); return
        self._results_cache[key] = result
        while len(self._results_cache) > 8:
            del self._results_cache[next(iter(self._results_cache))]
        self._loaded_key = key
        if self._last_result == (root, result):
            return
        self._last_result = (root, result)
        self.entries,self.nodes,node_totals,complete = result
        self.map.set_items(self.entries)
        self.radial.root = root; self.radial.nodes = self.nodes; self.radial.totals = node_totals; self.radial.set_items(self.entries)
        self.radial.animate_navigation(self._navigation_zoom)
        self._navigation_zoom = 0
        blocker = qt.QSignalBlocker(self.results)
        self.results.clear()
        total = node_totals.get(root, sum(size for _,size in self.entries))
        self._rows = {}
        def add_rows(items, parent=None):
            for path,size in items:
                item = qt.QTreeWidgetItem([path.name,format_size(size),f'{100*size/total:.1f}%' if total else '0%'])
                item.setData(0,qt.Qt.ItemDataRole.UserRole,path); item.setToolTip(0,str(path))
                item.setToolTip(2, 'Share of the current folder total')
                if parent is None: self.results.addTopLevelItem(item)
                else: parent.addChild(item)
                self._rows[path] = item
                add_rows(self.nodes.get(path, ()), item)
        add_rows(self.entries)
        blocker.unblock()
        self.summary.setText(f'{format_size(total)} · {len(self.entries):,} entries · '+
                             ('Partial index; chart fills as indexing progresses.' if not complete else 'Double-click folders to explore.') +
                             (' · Four levels; up to 3,000 entries. Gaps may be omitted entries; zero-byte folders have no area.'
                              if self.chart_selector.currentIndex() == 1 else '') +
                             (' · First 3,000 children shown; use List or Search for the full folder.' if len(self.entries) == 3000 else ''))
        self.select_path(self.selected_path) if self.selected_path else None

    def _finished(self):
        self.busy = False; self.operation.deleteLater()
        self.operation = None
        if self.closing: self.idle.emit()
        elif self.pending:
            self.pending = False; self.refresh()

    def stop(self):
        self.closing = True
        if self.busy: self.operation.requestInterruption()
        return self.busy

    def wait(self):
        if self.busy: self.operation.wait()
