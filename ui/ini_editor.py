"""Section tabs and key rows backed by an explicit-save source editor."""
from configparser import Error as ConfigError
from ..fileTypes.iniType import INIFile
from . import pyside as qt
from .text_editor import TextFileEditor
from ..configuration.ini_schema import key_type, mode_choices, parse_value, validate_values


class INISettingsEditor(TextFileEditor):
    """Edit a generic INI, optionally interpreting typed key suffixes.

    Pass typed_keys=True to enable ini_schema validation and boolean/mode controls.
    Ordinary INIs use string rows regardless of key names. The caller owns domain
    validation and applying saved settings; `saved(path)` signals a successful save.
    Create a QApplication before constructing this widget.
    """
    def __init__(self, path, parent=None, *, typed_keys=False):
        self.typed_keys = typed_keys
        self._building = True
        self._errors = {}
        self.fields = {}
        super().__init__(path, parent)
        self.tabs = qt.QTabWidget()
        self.sections = qt.QTabWidget()
        self.tabs.addTab(self.sections, 'Settings')
        raw = qt.QWidget()
        raw_layout = qt.QVBoxLayout(raw)
        self.layout().replaceWidget(self.text, self.tabs)
        raw_layout.addWidget(self.text)
        self.tabs.addTab(raw, 'Source')
        self.tabs.currentChanged.connect(self._switched)
        self.text.textChanged.connect(self._source_changed)
        self._building = False
        self._build_fields()

    def _key_type(self, key):
        return key_type(key) if self.typed_keys else (key, 'str')

    def _mode_choices(self, key, values):
        return mode_choices(key, values) if self.typed_keys else None

    def _source_changed(self):
        if not self._building and self.tabs.currentIndex() == 1:
            self._source_dirty = True

    def _build_fields(self):
        if self._original is None:
            self.tabs.setCurrentIndex(1)
            return
        self._building = True
        self._errors.clear()
        self.fields.clear()
        while self.sections.count():
            widget = self.sections.widget(0)
            self.sections.removeTab(0)
            widget.deleteLater()
        try:
            parser = INIFile.parse(self.text.toPlainText())
            sections = (['DEFAULT'] if parser.defaults() else []) + parser.sections()
            for section in sections:
                scroll = qt.QScrollArea()
                scroll.setWidgetResizable(True)
                body = qt.QWidget()
                form = qt.QFormLayout(body)
                form.setFieldGrowthPolicy(qt.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                values = dict(parser[section])
                for key, value in values.items():
                    label, kind = self._key_type(key)
                    choices = None
                    try:
                        choices = self._mode_choices(key, values)
                        parsed = parse_value(kind, value, choices=choices)
                        valid = True
                    except (ValueError, OverflowError):
                        valid = False
                    if kind == 'bool' and valid:
                        control = qt.QCheckBox()
                        control.setChecked(parsed)
                        control.toggled.connect(lambda checked, s=section, k=key: self._edit(s, k, 'true' if checked else 'false'))
                    elif kind == 'mode' and choices:
                        control = qt.QComboBox()
                        control.addItems(choices)
                        if value not in choices:
                            control.addItem(value)
                        control.setCurrentText(value)
                        control.currentTextChanged.connect(lambda v, s=section, k=key: self._edit(s, k, v))
                    else:
                        control = qt.QPlainTextEdit(value) if '\n' in value else qt.QLineEdit(value)
                        if isinstance(control, qt.QPlainTextEdit):
                            control.setMaximumHeight(100)
                            control.textChanged.connect(lambda c=control, s=section, k=key: self._edit(s, k, c.toPlainText()))
                        else:
                            control.textChanged.connect(lambda v, s=section, k=key: self._edit(s, k, v))
                    control.setAccessibleName(f'{section}: {label}')
                    control.setToolTip(f'{key} ({kind})' + (' — add ' + label + '_choices_list-str for dropdown choices' if kind == 'mode' and choices is None else ''))
                    field_label = qt.QLabel(label.replace('_', ' '))
                    field_label.setTextFormat(qt.Qt.TextFormat.PlainText)
                    form.addRow(field_label, control)
                    self.fields[section, key] = control
                scroll.setWidget(body)
                self.sections.addTab(scroll, section)
            self.status.setText('Edit settings, then Save. Source remains available for advanced edits.')
            self._source_dirty = False
        except (ConfigError, ValueError) as error:
            self.status.setText(f'Cannot display settings: {error}. Correct the INI in Source.')
            self.tabs.setCurrentIndex(1)
        finally:
            self._building = False

    def _edit(self, section, key, value):
        if self._building:
            return
        self.text.document().setModified(True)
        try:
            parser = INIFile.parse(self.text.toPlainText())
            values = dict(parser[section])
            parse_value(self._key_type(key)[1], value, choices=self._mode_choices(key, values))
            content = INIFile.updated_text(self.text.toPlainText(), {(section, key): value})
            self._errors.pop((section, key), None)
            self._building = True
            self.text.setPlainText(content)
            self.text.document().setModified(True)
            self._building = False
            self.status.setText('Unsaved settings.' if not self._errors else next(iter(self._errors.values())))
        except (ConfigError, ValueError, OverflowError) as error:
            self._errors[section, key] = f'[{section}] {key}: {error}'
            self.status.setText(self._errors[section, key])

    def _switched(self, index):
        if self._building:
            return
        if index == 1 and self._errors:
            self.status.setText('Correct invalid fields before switching to Source, or discard changes.')
            with qt.QSignalBlocker(self.tabs):
                self.tabs.setCurrentIndex(0)
        elif index == 0 and getattr(self, '_source_dirty', False):
            self._build_fields()

    def reload(self, *, initial=False):
        result = super().reload(initial=initial)
        if result and hasattr(self, 'tabs'):
            self._build_fields()
        return result

    def save(self):
        if self._errors:
            self.status.setText('Could not save: ' + next(iter(self._errors.values())))
            return False
        try:
            parser = INIFile.parse(self.text.toPlainText())
            if self.typed_keys:
                validate_values(parser)
        except (ConfigError, ValueError, OverflowError) as error:
            self.status.setText(f'Could not save: {error}')
            return False
        result = super().save()
        if result:
            self._build_fields()
        return result
