"""Explicit-save fields for repository defaults or sparse personal overrides."""
from configparser import Error
from .. import pyside as qt
from ...configuration.ini_schema import key_type, mode_choices, parse_value
from ..appearance.styling import STYLE_FIELDS, validate_style
from .font_preview import FontPreview


class LayeredSettingsEditor(qt.QWidget):
    saved = qt.Signal(object)

    def __init__(self, store, parent=None, *, scope='personal', sections=None, labels=None, validator=None):
        super().__init__(parent)
        self.store, self.scope = store, scope
        self.only_sections, self.labels = sections, labels or {}
        self.validator = validator
        self.fields, self.resets, self.indicators = {}, {}, {}
        self.font_previews = {}
        self.pending = {}
        self.building = False
        layout = qt.QVBoxLayout(self)
        self.path_label = qt.QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        self.sections = qt.QTabWidget()
        layout.addWidget(self.sections, 1)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = qt.QHBoxLayout()
        self.reload_button = qt.QPushButton('Reload')
        self.reload_button.clicked.connect(self.reload)
        self.save_button = qt.QPushButton('Save Settings')
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.reload_button)
        row.addStretch()
        row.addWidget(self.save_button)
        layout.addLayout(row)
        self.reload(initial=True)

    @property
    def path(self):
        return self.store.path(self.scope)

    def _bytes(self, path):
        return path.read_bytes() if path.exists() else None

    def reload(self, *, initial=False):
        if self.pending and not initial and not self.can_close():
            return False
        try:
            self.original = self.store.values(self.scope)
            self.defaults = self.store.values('application')
            self.overrides = self.store.overrides()
            self.snapshot = self._bytes(self.path)
            self.default_snapshot = self._bytes(self.store.defaults)
        except (OSError, UnicodeError, Error) as error:
            self.status.setText(f'Cannot read settings: {error}. The file has been preserved.')
            self.save_button.setEnabled(False)
            return False
        self.pending.clear()
        self.path_label.setText(str(self.path))
        self.path_label.setToolTip('Repository defaults shipped in releases' if self.scope == 'application'
                                   else 'Personal overrides; inherited values are not written to this file')
        self._build()
        self.status.setText('Software defaults: edits change this installation’s repository INI.'
                            if self.scope == 'application' else 'Inherited values follow software defaults. ↶ removes a personal override.')
        self.save_button.setEnabled(False)
        return True

    def _build(self):
        self.building = True
        while self.sections.count():
            widget = self.sections.widget(0)
            self.sections.removeTab(0)
            widget.deleteLater()
        self.fields.clear(); self.resets.clear(); self.indicators.clear()
        self.font_previews.clear()
        forms = {}
        for (section, key), value in self.original.items():
            if key.endswith('_choices_list-str'):
                continue  # Schema metadata supplies choices; it is not a preference.
            if (section, key) not in self.defaults:
                continue  # Saved window/session data is not a software setting.
            if self.only_sections is not None and section not in self.only_sections:
                continue
            if section not in forms:
                scroll = qt.QScrollArea()
                scroll.setWidgetResizable(True)
                body = qt.QWidget()
                forms[section] = qt.QFormLayout(body)
                forms[section].setFieldGrowthPolicy(qt.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                scroll.setWidget(body)
                self.sections.addTab(scroll, section)
            identity = section, key
            label, kind = key_type(key)
            values = {k: v for (s, k), v in self.original.items() if s == section}
            choices = mode_choices(key, values)
            if section == 'Styling' and key in STYLE_FIELDS:
                label, fallback, limits = STYLE_FIELDS[key]
                if key == 'theme_mode':
                    choices = limits
                if isinstance(fallback, int):
                    try:
                        validate_style(key, value)
                    except (ValueError, OverflowError):
                        control = None
                    else:
                        control = qt.QSpinBox()
                        control.setRange(*limits)
                        control.setValue(int(value))
                        control.valueChanged.connect(lambda v, i=identity: self._edit(i, str(v)))
                else:
                    control = None
            else:
                control = None
            if control is None and (kind == 'bool' or value.lower() in ('true', 'false')):
                control = qt.QCheckBox()
                control.setChecked(value.lower() in ('true', 'yes', 'on', '1'))
                control.toggled.connect(lambda v, i=identity: self._edit(i, 'true' if v else 'false'))
            elif control is None and choices:
                control = qt.QComboBox()
                control.addItems(choices)
                if value not in choices:
                    control.addItem(value)
                control.setCurrentText(value)
                control.currentTextChanged.connect(lambda v, i=identity: self._edit(i, v))
            elif control is None and section == 'Styling' and key.endswith('font_family_str'):
                control = qt.QComboBox()
                control.setEditable(True)
                control.setInsertPolicy(qt.QComboBox.InsertPolicy.NoInsert)
                control.setProperty('monospace_only', key == 'code_font_family_str')
                control.addItem('Automatic', '')
                for family in qt.QFontDatabase.families():
                    if key == 'code_font_family_str' and not qt.QFontDatabase.isFixedPitch(family):
                        continue
                    self._add_font(control, family)
                self._select_font(control, value)
                control.currentTextChanged.connect(lambda v, c=control, i=identity:
                    self._edit(i, '' if c.currentIndex() == 0 and v == 'Automatic' else v))
            elif control is None:
                if '\n' in value:
                    control = qt.QPlainTextEdit(value)
                    control.setMaximumHeight(120)
                    control.textChanged.connect(lambda c=control, i=identity: self._edit(i, c.toPlainText()))
                else:
                    control = qt.QLineEdit(value)
                    control.textChanged.connect(lambda v, i=identity: self._edit(i, v))
            label = self.labels.get(identity, label.replace('_', ' '))
            control.setAccessibleName(f'{section}: {label}')
            control.setToolTip(key)
            row = qt.QWidget()
            content = qt.QHBoxLayout(row)
            content.setContentsMargins(0, 0, 0, 0)
            content.addWidget(control, 1)
            if key.endswith('_color_str'):
                if not value:
                    control.setPlaceholderText('Automatic (theme)')
                choose = qt.QToolButton()
                choose.setText('…'); choose.setToolTip('Choose color')
                choose.clicked.connect(lambda checked=False, c=control: self._color(c))
                content.addWidget(choose)
            indicator = qt.QLabel()
            indicator.setMinimumWidth(65)
            content.addWidget(indicator)
            reset = qt.QToolButton()
            reset.setText('↶')
            reset.setToolTip('Use software default' if self.scope == 'personal' else 'Revert this unsaved field')
            reset.setAccessibleName(f'Reset {label} to default')
            reset.clicked.connect(lambda checked=False, i=identity: self._reset(i))
            content.addWidget(reset)
            self.fields[identity], self.resets[identity], self.indicators[identity] = control, reset, indicator
            forms[section].addRow(label, row)
            if section == 'Styling' and key.endswith('font_family_str'):
                role = key.removesuffix('_font_family_str')
                self.font_previews[role] = FontPreview(role)
                forms[section].addRow('', self.font_previews[role])
            self._state(identity)
        self.building = False
        self._update_font_previews()

    def _add_font(self, control, family):
        control.addItem(family, family)
        font = qt.QFont(control.font())
        font.setFamily(family)
        control.setItemData(control.count() - 1, font, qt.Qt.ItemDataRole.FontRole)

    def _select_font(self, control, family):
        index = control.findData(family)
        if index < 0 and family:
            if control.property('monospace_only') and not qt.QFontDatabase.isFixedPitch(family):
                control.setEditText(family)
                return
            self._add_font(control, family)
            index = control.count() - 1
        control.setCurrentIndex(max(0, index))

    def _update_font_previews(self):
        if not self.font_previews:
            return
        from ..appearance.styling import styling
        from ..code_editor.widget import monospace_font
        values = {key: value for (section, key), value in self.original.items() if section == 'Styling'}
        for (section, key), value in self.pending.items():
            if section == 'Styling':
                values[key] = self.defaults.get((section, key), '') if value is None else value
        ui_font = qt.QFont(styling().base_font)
        if values.get('ui_font_family_str', '').strip():
            ui_font.setFamily(values['ui_font_family_str'].strip())
        for role, preview in self.font_previews.items():
            font = monospace_font() if role == 'code' else qt.QFont(ui_font)
            family_key, size_key = f'{role}_font_family_str', f'{role}_font_size_int'
            family = values.get(family_key, STYLE_FIELDS[family_key][1]).strip()
            if family:
                font.setFamily(family)
            try:
                validate_style(size_key, values.get(size_key, str(STYLE_FIELDS[size_key][1])))
                font.setPointSize(int(values.get(size_key, STYLE_FIELDS[size_key][1])))
            except (ValueError, OverflowError):
                font.setPointSize(STYLE_FIELDS[size_key][1])
            preview.set_sample_font(font)
            control = self.fields['Styling', family_key]
            # The editable field is an exception to the normal settings font.
            selected_font = qt.QFont(font)
            selected_font.setPointSize(qt.QApplication.font().pointSize())
            control.lineEdit().setFont(selected_font)

    def _color(self, control):
        color = qt.QColorDialog.getColor(qt.QColor(control.text()), self, 'Choose color')
        if color.isValid():
            control.setText(color.name())

    def _state(self, identity):
        override = identity in self.overrides
        if identity in self.pending:
            override = self.pending[identity] is not None
        self.indicators[identity].setText(('Override' if override else 'Inherited') if self.scope == 'personal' else '')
        self.resets[identity].setEnabled(override if self.scope == 'personal' else identity in self.pending)

    def _edit(self, identity, value):
        if self.building:
            return
        baseline = self.overrides.get(identity) if self.scope == 'personal' else self.original.get(identity)
        if value == baseline:
            self.pending.pop(identity, None)
        else:
            self.pending[identity] = value
        self._state(identity)
        self.save_button.setEnabled(bool(self.pending))
        self.status.setText('Unsaved settings.' if self.pending else '')
        self._update_font_previews()

    def _reset(self, identity):
        value = self.defaults.get(identity, '') if self.scope == 'personal' else self.original[identity]
        self.building = True
        control = self.fields[identity]
        with qt.QSignalBlocker(control):
            if isinstance(control, qt.QCheckBox):
                control.setChecked(value.lower() in ('true', 'yes', 'on', '1'))
            elif isinstance(control, qt.QSpinBox):
                try:
                    control.setValue(int(value))
                except ValueError:
                    control.setValue(STYLE_FIELDS[identity[1]][1])
            elif isinstance(control, qt.QComboBox):
                if identity[0] == 'Styling' and identity[1].endswith('font_family_str'):
                    self._select_font(control, value)
                else:
                    control.setCurrentText(value)
            elif isinstance(control, qt.QPlainTextEdit):
                control.setPlainText(value)
            else:
                control.setText(value)
        self.building = False
        if self.scope == 'personal' and identity in self.overrides:
            self.pending[identity] = None
        else:
            self.pending.pop(identity, None)
        self._state(identity)
        self.save_button.setEnabled(bool(self.pending))
        self.status.setText('Unsaved settings.' if self.pending else '')
        self._update_font_previews()

    def save(self):
        if not self.pending:
            return True
        try:
            if self._bytes(self.store.defaults) != self.default_snapshot:
                raise OSError('Software defaults changed on disk; reload before saving')
            effective = dict(self.original)
            effective.update({key: value if value is not None else self.defaults.get(key, '')
                              for key, value in self.pending.items()})
            for (section, key), value in self.pending.items():
                if value is None:
                    continue
                if section == 'Styling' and key in STYLE_FIELDS:
                    validate_style(key, value)
                else:
                    values = {k: v for (s, k), v in effective.items() if s == section}
                    parse_value(key_type(key)[1], value, choices=mode_choices(key, values))
            if self.validator is not None:
                self.validator(effective)
            self.store.save(self.pending, scope=self.scope, expected=(self.snapshot,))
        except (OSError, UnicodeError, Error, ValueError, OverflowError) as error:
            self.status.setText(f'Could not save settings: {error}')
            return False
        self.pending.clear()
        self.reload(initial=True)
        self.saved.emit(self.path)
        self.status.setText('Settings saved.')
        return True

    def can_close(self):
        if not self.pending:
            return True
        answer = qt.QMessageBox.question(self, 'Unsaved settings', 'Save changes to settings?',
            qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel)
        if answer == qt.QMessageBox.StandardButton.Save:
            return self.save()
        if answer == qt.QMessageBox.StandardButton.Discard:
            self.pending.clear()
            self.reload(initial=True)
            return True
        return False
