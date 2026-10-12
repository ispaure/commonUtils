"""Local typography samples; browsing settings never changes live application fonts."""
from .. import pyside as qt


class FontPreview(qt.QGroupBox):
    def __init__(self, role, parent=None):
        super().__init__('Preview (before saving)', parent)
        self.setProperty('font_preview', True)
        self.setAccessibleName(f'{role.capitalize()} font preview')
        layout = qt.QVBoxLayout(self)
        self.sample = qt.QWidget(self)
        content = qt.QVBoxLayout(self.sample)
        content.setContentsMargins(0, 0, 0, 0)
        self.editor = None
        if role == 'code':
            self.editor = qt.QPlainTextEdit()
            self.editor.setReadOnly(True)
            self.editor.setPlainText('def greet(name):\n    message = f"Hello, {name}!"\n    return message\n\nprint(greet("World"))')
            self.editor.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.NoWrap)
            self.editor.setFixedHeight(140)
            content.addWidget(self.editor)
        elif role == 'browser':
            path = qt.QLineEdit('/Projects/Example')
            path.setReadOnly(True)
            content.addWidget(path)
            tree = qt.QTreeWidget()
            tree.setHeaderLabels(['Name', 'Size', 'Type'])
            tree.addTopLevelItems([
                qt.QTreeWidgetItem(['Documents', '—', 'Folder']),
                qt.QTreeWidgetItem(['README.md', '2 KB', 'Markdown']),
                qt.QTreeWidgetItem(['main.py', '4 KB', 'Python']),
            ])
            tree.setRootIsDecorated(False)
            tree.setColumnWidth(0, 180)
            tree.setFixedHeight(145)
            content.addWidget(tree)
        elif role == 'reading':
            text = qt.QLabel('The quick brown fox jumps over the lazy dog.\n'
                            'A quiet morning, a good book, and a new chapter.\n'
                            'ABCDEFGHIJKLMNOPQRSTUVWXYZ · 0123456789')
            text.setWordWrap(True)
            text.setTextFormat(qt.Qt.TextFormat.PlainText)
            content.addWidget(text)
        else:
            content.addWidget(qt.QLabel('Settings · Appearance · Preferences'))
            row = qt.QHBoxLayout()
            row.addWidget(qt.QPushButton('Save Settings'))
            row.addWidget(qt.QPushButton('Cancel'))
            row.addStretch()
            content.addLayout(row)
        layout.addWidget(self.sample)

    def set_sample_font(self, font):
        self.sample.setFont(font)
        for widget in self.sample.findChildren(qt.QWidget):
            widget.setFont(font)
        if self.editor is not None:
            self.editor.document().setDefaultFont(font)
