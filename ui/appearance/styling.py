"""Shared application, browser, reading and code fonts with live settings reload.

Opt in with apply_styling after creating QApplication. Components bind their role
without depending on the host's settings window or feature registry.
"""
from weakref import WeakKeyDictionary, WeakMethod, WeakSet, ref

from shiboken6 import isValid
from .. import pyside as qt
from .typography import point_size, setting_size
from configparser import Error
from .font_families import supported_font_family, font_database_available

STYLE_FIELDS = {
    'theme_mode': ('Theme', 'system', ('system', 'light', 'dark')),
    'accent_color_str': ('Accent color', '#75a7ff', None),
    'dark_tint_int': ('Dark surface tint (%)', 6, (0, 20)),
    'ui_font_family_str': ('Interface and dialog font', '', None),
    'ui_font_size_int': ('Interface and dialog size (pt)', 10, (7, 24)),
    'browser_font_family_str': ('File browser font', '', None),
    'browser_font_size_int': ('File browser size (pt)', 10, (7, 24)),
    'reading_font_family_str': ('Reading font (Markdown and EPUB)', 'Arial', None),
    'reading_font_size_int': ('Reading size (pt)', 10, (7, 24)),
    'code_font_family_str': ('Code font (editors and Markdown blocks)', '', None),
    'code_font_size_int': ('Code size (pt)', 9, (7, 24)),
}


def style_values():
    from ...configuration.layered import shared_settings, read_values
    store = shared_settings()
    layers = []
    for path in (store.personal, store.defaults):
        try:
            layers.append(read_values(path))
        except (OSError, UnicodeError, Error):
            layers.append({})
    values = {}
    for key, (_, default, choices) in STYLE_FIELDS.items():
        values[key] = default
        for layer in layers:
            if ('Styling', key) not in layer:
                continue
            raw = layer['Styling', key]
            try:
                validate_style(key, raw)
                values[key] = int(raw) if isinstance(default, int) else raw
                break
            except (ValueError, OverflowError):
                continue
    return values


def validate_style(key, value):
    _, default, choices = STYLE_FIELDS[key]
    if isinstance(default, int):
        if not choices[0] <= int(value) <= choices[1]:
            raise ValueError(f'Choose a value between {choices[0]} and {choices[1]}')
    elif key == 'accent_color_str' and not qt.QColor(value).isValid():
        raise ValueError('Enter a valid color, such as #75a7ff')
    elif key == 'theme_mode' and value not in choices:
        raise ValueError('Choose System, Light or Dark')
    elif key.endswith('font_family_str') and not supported_font_family(value):
        raise ValueError('Choose a scalable outline font supported on Windows, or Automatic')
    elif (key == 'code_font_family_str' and value.strip() and font_database_available()
          and not qt.QFontDatabase.isFixedPitch(value.strip())):
        raise ValueError('Choose a monospace font for code, or Automatic')


class Styling(qt.QObject):
    changed = qt.Signal()

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.base_font = qt.QFont(app.font())
        self._font_cache = {}
        self.views = WeakKeyDictionary()
        self._updating_widgets = WeakSet()
        self.application_controls = WeakSet()
        self.values = {}
        self.apply_application = False
        self.code_font = CodeFontController(self)
        self.reload()
        from ...configuration.layered import shared_settings
        from ..settings.monitor import subscribe_settings
        store = shared_settings()
        self._settings_subscription = subscribe_settings((store.defaults, store.personal), self.reload, self)

    def font(self, role):
        if role not in ('ui', 'browser', 'reading', 'code'):
            raise ValueError('Unknown styling font role')
        family = self.values[f'{role}_font_family_str'].strip()
        size = point_size(self.values[f'{role}_font_size_int'])
        base = self.app.font() if role in ('browser', 'reading') else self.base_font
        key = (role, family, size, base.key())
        if key in self._font_cache:
            return qt.QFont(self._font_cache[key])
        if role == 'code':
            from ..code_editor.widget import monospace_font
            font = monospace_font()
        else:
            font = qt.QFont(base)
        if family:
            font.setFamily(family)
        font.setPointSizeF(size)
        self._font_cache[key] = qt.QFont(font)
        return font

    def bind(self, widget, role, callback=None):
        if callback is not None and getattr(callback, '__self__', None) is widget:
            callback = WeakMethod(callback)
        self.views[widget] = (role, callback)
        self._update(widget, role, callback)

    def _update(self, widget, role, callback):
        if not isValid(widget) or widget in self._updating_widgets:
            return
        self._updating_widgets.add(widget)
        try:
            self._update_font(widget, role, callback)
        finally:
            self._updating_widgets.discard(widget)

    def _update_font(self, widget, role, callback):
        font = self.font(role)
        font_changed = widget.font() != font
        if font_changed:
            widget.setFont(font)
        if isinstance(widget, (qt.QTextEdit, qt.QPlainTextEdit)):
            modified = widget.document().isModified()
            if widget.document().defaultFont() != font:
                widget.document().setDefaultFont(font)
            if font_changed and hasattr(widget, 'update_tab_width'):
                widget.update_tab_width()
            if font_changed and hasattr(widget, 'update_gutter'):
                widget.update_gutter()
            widget.document().setModified(modified)
        if callback is not None:
            if isinstance(callback, WeakMethod):
                callback = callback()
        if callback is not None:
            callback()

    def _bind_application_control(self, widget):
        if not isinstance(widget, (qt.QAbstractButton, qt.QMenu, qt.QMenuBar)):
            return
        if not isValid(widget):
            return
        if widget in self.views and widget not in self.application_controls:
            return  # Respect explicit component bindings.
        role = 'ui'
        parent = widget.parentWidget()
        while parent is not None:
            if parent.property('font_preview'):
                return  # Pending preview fonts remain local to settings samples.
            if isinstance(widget, qt.QAbstractButton) and parent in self.views:
                role = self.views[parent][0]
                break
            parent = parent.parentWidget()
        self.application_controls.add(widget)
        if widget in self.views and self.views[widget] == (role, None):
            return
        self.bind(widget, role)

    def eventFilter(self, watched, event):
        if (self.apply_application and event.type() == qt.QEvent.Type.FontChange
                and watched in self.views and watched not in self._updating_widgets):
            role, callback = self.views[watched]
            expected = self.font(role)
            actual = watched.font()
            # Code editors change their own size while zooming; their controller
            # handles that signal. Other bound roles must survive repolishing.
            if (role != 'code' or isinstance(watched, (qt.QAbstractButton, qt.QMenu, qt.QMenuBar))) and (
                    actual.family() != expected.family() or actual.pointSizeF() != expected.pointSizeF()):
                self._update(watched, role, callback)
        if self.apply_application and event.type() in (qt.QEvent.Type.Polish, qt.QEvent.Type.Show):
            self._bind_application_control(watched)
        return False

    def reload(self):
        values = style_values()
        if values == self.values:
            return
        previous = self.values
        initial = not previous
        self.values = values
        self._font_cache.clear()
        controller = getattr(self.app, '_commonutils_theme', None)
        if controller is not None and not initial and self.apply_application:
            if values['theme_mode'] != previous['theme_mode']:
                controller.set_mode(values['theme_mode'])
            else:
                controller._apply()
        if self.apply_application and self.app.font() != self.font('ui'):
            self.app.setFont(self.font('ui'))
        for widget, (role, callback) in tuple(self.views.items()):
            self._update(widget, role, callback)
        self.changed.emit()


def styling(app=None):
    app = app or qt.QApplication.instance()
    if app is None:
        raise RuntimeError('Create QApplication before requesting styling')
    controller = getattr(app, '_commonutils_styling', None)
    if controller is None:
        controller = app._commonutils_styling = Styling(app)
    return controller


def bind_font(widget, role, callback=None):
    styling().bind(widget, role, callback)


def apply_styling(app=None):
    """Host opt-in: apply the UI/dialog font globally and reload saved styling live."""
    controller = styling(app)
    controller.apply_application = True
    controller.app.setFont(controller.font('ui'))
    controller.app.installEventFilter(controller)
    for widget in controller.app.allWidgets():
        controller._bind_application_control(widget)
    return controller


class CodeFontController:
    """One live code family/size across editors, diffs and Markdown code."""
    def __init__(self, controller):
        self.controller = controller
        self.views = WeakSet()
        self.updating = False

    @property
    def size(self):
        return self.controller.values['code_font_size_int']

    def bind(self, editor):
        if editor not in self.views:
            self.views.add(editor)
            weak = ref(editor)
            if hasattr(editor, 'zoom_changed'):
                editor.zoom_changed.connect(lambda: self.changed(weak()))
        self.controller.bind(editor, 'code')

    def changed(self, editor):
        if editor is not None and isValid(editor) and not self.updating:
            self.set_size(setting_size(editor.font()))

    def set_size(self, size, *, save=True, notify=True):
        from ...configuration.layered import shared_settings
        size = max(7, min(24, round(size)))
        self.updating = True
        try:
            if save:
                shared_settings().save({('Styling', 'code_font_size_int'): str(size)})
                self.controller.reload()
            else:
                self.controller.values['code_font_size_int'] = size
                for widget, (role, callback) in tuple(self.controller.views.items()):
                    if role == 'code':
                        self.controller._update(widget, role, callback)
            if notify:
                for editor in tuple(self.views):
                    if isValid(editor) and hasattr(editor, 'zoom_changed'):
                        editor.zoom_changed.emit()
        finally:
            self.updating = False
