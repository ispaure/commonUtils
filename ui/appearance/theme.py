"""Opt-in Slate appearance using Qt Fusion, palettes and centralized stylesheet.

Importing this module never changes an application. Call apply_theme(app) once;
the returned controller supports system/light/dark selection without restarting.
"""
from dataclasses import dataclass, replace
from .. import pyside as qt
from ...configuration.settings import get_setting


@dataclass(frozen=True)
class ThemeColors:
    window: str
    surface: str
    alternate: str
    text: str
    muted: str
    border: str
    accent: str
    selected_text: str
    hover: str
    selection_background: str = ''


SLATE_LIGHT = ThemeColors('#f0f2f6', '#ffffff', '#f5f7fa', '#202838', '#606b7c',
                          '#c5cedb', '#2563eb', '#ffffff', '#e3eaf7')
SLATE_DARK = ThemeColors('#1c1f26', '#252a34', '#2d3340', '#eef1f7', '#a6b0c0',
                         '#495366', '#75a7ff', '#ffffff', '#35425a', '#356ac3')


def configured_colors(dark):
    """Tint neutral dark surfaces with the accent and choose readable selection text."""
    from .styling import style_values
    values = style_values()
    colors = SLATE_DARK if dark else SLATE_LIGHT
    accent = qt.QColor(values['accent_color_str'])
    def luminance(color):
        channels = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4
                    for channel in color.getRgbF()[:3]]
        return sum(channel * weight for channel, weight in zip(channels, (.2126, .7152, .0722)))
    def text_on(color):
        return '#000000' if luminance(color) > .179 else '#ffffff'
    selection = accent
    changes = dict(accent=accent.name(), selection_background=selection.name(), selected_text=text_on(selection))
    if dark:
        amount = values['dark_tint_int'] / 100
        for name, neutral in (('window', '#1e1e1e'), ('surface', '#282828'), ('alternate', '#303030'),
                              ('border', '#505050'), ('hover', '#393939')):
            base = qt.QColor(neutral)
            changes[name] = qt.QColor(*(round(a * (1 - amount) + b * amount)
                                       for a, b in zip(base.getRgb()[:3], accent.getRgb()[:3]))).name()
    return replace(colors, **changes)


def theme_palette(colors):
    palette = qt.QPalette()
    role = qt.QPalette.ColorRole
    for name, value in {
        role.Window: colors.window, role.Base: colors.surface,
        role.AlternateBase: colors.alternate, role.Button: colors.surface,
        role.ToolTipBase: colors.surface, role.ToolTipText: colors.text,
        role.WindowText: colors.text, role.Text: colors.text, role.ButtonText: colors.text,
        role.Highlight: colors.selection_background or colors.accent, role.HighlightedText: colors.selected_text,
        role.Link: colors.accent, role.LinkVisited: colors.accent,
        role.BrightText: '#ff7373', role.PlaceholderText: colors.muted,
        role.Light: colors.surface, role.Midlight: colors.hover,
        role.Mid: colors.border, role.Dark: colors.border, role.Shadow: colors.window,
    }.items():
        palette.setColor(name, qt.QColor(value))
    for name in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(qt.QPalette.ColorGroup.Disabled, name, qt.QColor(colors.muted))
    return palette


def theme_stylesheet(c):
    # Keep accent/tint changes in the palette; replacing application QSS
    # repolishes every widget, including hidden pages and font dropdowns.
    return f'''
        QToolTip {{ color: palette(text); background: palette(base); border: 1px solid palette(mid); padding: 5px; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QAbstractItemView {{
            background: palette(base); color: palette(text); border: 1px solid palette(mid); border-radius: 6px;
            selection-background-color: palette(highlight); selection-color: palette(highlighted-text);
        }}
        QLineEdit {{ padding: 1px 5px; }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid palette(link); }}
        QAbstractItemView::item {{ padding: 4px; margin: 0px; border: none; }}
        QAbstractItemView::item:hover {{ background: palette(midlight); padding: 4px; margin: 0px; border: none; }}
        QAbstractItemView::item:selected {{ background: palette(highlight); color: palette(highlighted-text); padding: 4px; margin: 0px; border: none; }}
        QHeaderView::section {{ background: palette(window); color: palette(text); border: none;
            border-bottom: 1px solid palette(mid); padding: 7px; }}
        QPushButton, QComboBox {{ background: palette(base); color: palette(text); border: 1px solid palette(mid);
            border-radius: 6px; padding: 2px 8px; }}
        QComboBox, QAbstractSpinBox {{ padding: 1px 8px; border: 1px solid palette(mid); border-radius: 6px;
            background: palette(base); color: palette(text); }}
        QPushButton:hover, QComboBox:hover, QToolButton:hover {{ background: palette(midlight); }}
        QPushButton:pressed, QPushButton:checked {{ background: palette(highlight); color: palette(highlighted-text); }}
        QPushButton:focus, QComboBox:focus, QToolButton:focus {{ border: 1px solid palette(link); }}
        QPushButton:disabled, QComboBox:disabled {{ color: {c.muted}; }}
        QComboBox QLineEdit, QAbstractSpinBox QLineEdit,
        QComboBox QLineEdit:focus, QAbstractSpinBox QLineEdit:focus {{
            border: none; border-radius: 0px; padding: 0px; background: transparent; }}
        QToolButton {{ border: 1px solid transparent; border-radius: 4px; padding: 2px; }}
        QGroupBox {{ border: 1px solid palette(mid); border-radius: 6px; margin-top: 12px; padding-top: 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0px 4px; }}
        QTabWidget::pane {{ border: 1px solid palette(mid); }}
        QTabBar::tab {{ background: palette(window); color: {c.muted}; padding: 8px 14px;
            border: none; border-bottom: 3px solid transparent; }}
        QTabBar::tab:hover {{ background: palette(midlight); color: palette(text); }}
        QTabBar::tab:selected {{ background: palette(base); color: palette(text);
            border-bottom: 3px solid palette(link); font-weight: bold; }}
        QProgressBar {{ border: none; background: palette(alternate-base); border-radius: 4px;
            min-height: 16px; text-align: center; color: palette(text); }}
        QProgressBar::chunk {{ background: palette(link); border-radius: 4px; }}
        QMenu {{ background: palette(base); color: palette(text); border: 1px solid palette(mid); }}
        QMenu::item {{ padding: 6px 22px; }}
        QMenu::item:selected {{ background: palette(highlight); color: palette(highlighted-text); }}
        QSplitter::handle {{ background: palette(window); }}
    '''


class ThemeController(qt.QObject):
    changed = qt.Signal(str)

    def __init__(self, app, mode):
        super().__init__(app)
        self.app = app
        self._base_stylesheet = app.styleSheet()
        self._initial_dark = app.palette().color(qt.QPalette.ColorRole.Window).lightness() < 128
        # Stylesheets wrap the underlying style; their wrapper has no Fusion
        # object name. Select the engine once, before installing our stylesheet.
        if app.style().objectName().lower() != 'fusion':
            app.setStyle('Fusion')
        self._applied_colors = None
        self._applied_palette = None
        self.mode = 'system'
        self._applying = False
        self._system_timer = qt.QTimer(self)
        self._system_timer.setSingleShot(True)
        self._system_timer.timeout.connect(self._apply)
        app.styleHints().colorSchemeChanged.connect(self._system_changed)
        self.set_mode(mode)

    def _system_changed(self, scheme):
        if self.mode == 'system':
            self._system_timer.start(0)

    def set_mode(self, mode):
        if mode not in ('system', 'light', 'dark'):
            raise ValueError('Theme mode must be system, light or dark')
        self.mode = mode
        self._apply()

    def _apply(self):
        if self._applying:
            return
        self._applying = True
        try:
            self._apply_colors()
        finally:
            self._applying = False

    def _apply_colors(self):
        scheme = self.app.styleHints().colorScheme()
        dark = (self.mode == 'dark' or self.mode == 'system' and
                (scheme == qt.Qt.ColorScheme.Dark or scheme == qt.Qt.ColorScheme.Unknown and self._initial_dark))
        self.colors = configured_colors(dark)
        palette = theme_palette(self.colors)
        stylesheet = theme_stylesheet(self.colors) + '\n' + self._base_stylesheet
        if (self.colors == self._applied_colors and self.app.styleSheet() == stylesheet
                and self.app.palette() == self._applied_palette):
            return
        changed = False
        if self.app.palette() != palette:
            self.app.setPalette(palette)
            changed = True
        if self.app.styleSheet() != stylesheet:
            self.app.setStyleSheet(stylesheet)
            changed = True
        elif changed:
            # QSS caches palette() brushes in its render rules. Invalidate the
            # application caches without repolishing every widget/font/layout.
            style = self.app.style()
            style.unpolish(self.app)
            style.polish(self.app)
        if not changed:
            return
        self._applied_colors = self.colors
        self._applied_palette = qt.QPalette(self.app.palette())
        self.changed.emit('dark' if dark else 'light')


def apply_theme(app=None, *, mode=None):
    """Opt into Slate. INI [Theme] mode defaults to system; other hosts stay unchanged."""
    app = app or qt.QApplication.instance()
    if app is None:
        raise RuntimeError('Create QApplication before applying a theme')
    if mode is None:
        mode = get_setting('Styling', 'theme_mode', get_setting('Theme', 'mode', 'system')).strip().lower()
        if mode not in ('system', 'light', 'dark'):
            mode = 'system'
    controller = getattr(app, '_commonutils_theme', None)
    if controller is None:
        controller = ThemeController(app, mode)
        app._commonutils_theme = controller
    else:
        controller.set_mode(mode)
    return controller
