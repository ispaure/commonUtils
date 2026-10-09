"""Opt-in Slate appearance using Qt Fusion, palettes and centralized stylesheet.

Importing this module never changes an application. Call apply_theme(app) once;
the returned controller supports system/light/dark selection without restarting.
"""
from dataclasses import dataclass
from . import pyside as qt
from ..settings import get_setting


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


SLATE_LIGHT = ThemeColors('#f0f2f6', '#ffffff', '#f5f7fa', '#202838', '#606b7c',
                          '#c5cedb', '#2563eb', '#ffffff', '#e3eaf7')
SLATE_DARK = ThemeColors('#1c1f26', '#252a34', '#2d3340', '#eef1f7', '#a6b0c0',
                         '#495366', '#75a7ff', '#101620', '#35425a')


def theme_palette(colors):
    palette = qt.QPalette()
    role = qt.QPalette.ColorRole
    for name, value in {
        role.Window: colors.window, role.Base: colors.surface,
        role.AlternateBase: colors.alternate, role.Button: colors.surface,
        role.ToolTipBase: colors.surface, role.ToolTipText: colors.text,
        role.WindowText: colors.text, role.Text: colors.text, role.ButtonText: colors.text,
        role.Highlight: colors.accent, role.HighlightedText: colors.selected_text,
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
    return f'''
        QToolTip {{ color: {c.text}; background: {c.surface}; border: 1px solid {c.border}; padding: 5px; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QAbstractItemView {{
            background: {c.surface}; color: {c.text}; border: 1px solid {c.border}; border-radius: 6px;
            selection-background-color: {c.accent}; selection-color: {c.selected_text};
        }}
        QLineEdit {{ padding: 6px; min-height: 20px; }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {c.accent}; }}
        QAbstractItemView::item {{ padding: 4px; margin: 0px; border: none; }}
        QAbstractItemView::item:hover {{ background: {c.hover}; padding: 4px; margin: 0px; border: none; }}
        QAbstractItemView::item:selected {{ background: {c.accent}; color: {c.selected_text}; padding: 4px; margin: 0px; border: none; }}
        QHeaderView::section {{ background: {c.window}; color: {c.text}; border: none;
            border-bottom: 1px solid {c.border}; padding: 7px; }}
        QPushButton, QComboBox {{ background: {c.surface}; color: {c.text}; border: 1px solid {c.border};
            border-radius: 6px; padding: 6px 10px; min-height: 20px; }}
        QPushButton:hover, QComboBox:hover, QToolButton:hover {{ background: {c.hover}; }}
        QPushButton:pressed, QPushButton:checked {{ background: {c.accent}; color: {c.selected_text}; }}
        QPushButton:focus, QComboBox:focus, QToolButton:focus {{ border: 1px solid {c.accent}; }}
        QPushButton:disabled, QComboBox:disabled {{ color: {c.muted}; }}
        QToolButton {{ border: 1px solid transparent; border-radius: 4px; padding: 2px; }}
        QGroupBox {{ border: 1px solid {c.border}; border-radius: 6px; margin-top: 12px; padding-top: 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0px 4px; }}
        QTabWidget::pane {{ border: 1px solid {c.border}; }}
        QTabBar::tab {{ background: {c.window}; color: {c.muted}; padding: 8px 14px;
            border: none; border-bottom: 3px solid transparent; }}
        QTabBar::tab:hover {{ background: {c.hover}; color: {c.text}; }}
        QTabBar::tab:selected {{ background: {c.surface}; color: {c.text};
            border-bottom: 3px solid {c.accent}; font-weight: bold; }}
        QProgressBar {{ border: none; background: {c.alternate}; border-radius: 4px;
            min-height: 16px; text-align: center; color: {c.text}; }}
        QProgressBar::chunk {{ background: {c.accent}; border-radius: 4px; }}
        QMenu {{ background: {c.surface}; color: {c.text}; border: 1px solid {c.border}; }}
        QMenu::item {{ padding: 6px 22px; }}
        QMenu::item:selected {{ background: {c.accent}; color: {c.selected_text}; }}
        QSplitter::handle {{ background: {c.window}; }}
    '''


class ThemeController(qt.QObject):
    changed = qt.Signal(str)

    def __init__(self, app, mode):
        super().__init__(app)
        self.app = app
        self._base_stylesheet = app.styleSheet()
        self._initial_dark = app.palette().color(qt.QPalette.ColorRole.Window).lightness() < 128
        self.mode = 'system'
        app.styleHints().colorSchemeChanged.connect(self._system_changed)
        self.set_mode(mode)

    def _system_changed(self, scheme):
        if self.mode == 'system':
            self._apply()

    def set_mode(self, mode):
        if mode not in ('system', 'light', 'dark'):
            raise ValueError('Theme mode must be system, light or dark')
        self.mode = mode
        self._apply()

    def _apply(self):
        scheme = self.app.styleHints().colorScheme()
        dark = (self.mode == 'dark' or self.mode == 'system' and
                (scheme == qt.Qt.ColorScheme.Dark or scheme == qt.Qt.ColorScheme.Unknown and self._initial_dark))
        self.colors = SLATE_DARK if dark else SLATE_LIGHT
        self.app.setStyle('Fusion')
        self.app.setPalette(theme_palette(self.colors))
        self.app.setStyleSheet(theme_stylesheet(self.colors) + '\n' + self._base_stylesheet)
        self.changed.emit('dark' if dark else 'light')


def apply_theme(app=None, *, mode=None):
    """Opt into Slate. INI [Theme] mode defaults to system; other hosts stay unchanged."""
    app = app or qt.QApplication.instance()
    if app is None:
        raise RuntimeError('Create QApplication before applying a theme')
    if mode is None:
        mode = get_setting('Theme', 'mode', 'system').strip().lower()
        if mode not in ('system', 'light', 'dark'):
            mode = 'system'
    controller = getattr(app, '_commonutils_theme', None)
    if controller is None:
        controller = ThemeController(app, mode)
        app._commonutils_theme = controller
    else:
        controller.set_mode(mode)
    return controller
