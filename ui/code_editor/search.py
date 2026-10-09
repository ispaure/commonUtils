"""Nonmodal, debounced document search with bounded PCRE work off the GUI thread."""
from dataclasses import dataclass
import re
from .. import pyside as qt
from ..operation_progress import OperationProgress

MATCH_LIMIT=50000


@dataclass(frozen=True)
class Match:
    start:int
    length:int
    replacement:str


def expanded_replacement(value,match):
    def expand(token):
        group=token[1] or token[2] or token[3] or token[4]
        if group is not None:
            key=int(group) if group.isdigit() else group
            if isinstance(key,int) and key>match.lastCapturedIndex():raise ValueError('Replacement references a missing capture group.')
            if isinstance(key,str) and key not in match.regularExpression().namedCaptureGroups():raise ValueError('Replacement references a missing named group.')
            return match.captured(key)
        return {'n':'\n','t':'\t','r':'\n','\\':'\\'}.get(token[5],token[5])
    return re.sub(r'\\g<([^>]+)>|\\([0-9]+)|\$\{([^}]+)\}|\$([0-9]+)|\\(.)',expand,value)


def find_matches(text,query,replacement='',*,case=False,whole=False,regex=False,scope=None,cancelled=lambda:False):
    if not query:return [],False
    if len(query)>2048:raise ValueError('Search pattern exceeds 2,048 characters.')
    pattern=query if regex else qt.QRegularExpression.escape(query)
    if whole:pattern=r'\b(?:'+pattern+r')\b'
    expression=qt.QRegularExpression('(*LIMIT_MATCH=100000)(*LIMIT_DEPTH=1000)'+pattern)
    options=qt.QRegularExpression.PatternOption.UseUnicodePropertiesOption|qt.QRegularExpression.PatternOption.MultilineOption
    if not case:options|=qt.QRegularExpression.PatternOption.CaseInsensitiveOption
    expression.setPatternOptions(options)
    if not expression.isValid():raise ValueError(expression.errorString())
    iterator=expression.globalMatch(text,scope[0] if scope else 0);result=[]
    while iterator.hasNext():
        if cancelled():return [],False
        match=iterator.next();start=match.capturedStart();length=match.capturedLength()
        if scope and start+length>scope[1]:
            if start>scope[1]:break
            continue
        result.append(Match(start,length,expanded_replacement(replacement,match) if regex else replacement))
        if len(result)>=MATCH_LIMIT:return result,True
    return result,False


class SearchPanel(qt.QWidget):
    idle=qt.Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.editor=None;self.matches=[];self.truncated=False;self.scope=None
        self._pending=False;self._generation=0;self._signature=None
        layout=qt.QVBoxLayout(self);layout.setContentsMargins(0,2,0,4)
        row=qt.QHBoxLayout();self.query=qt.QLineEdit();self.query.setPlaceholderText('Find in this document');self.query.setAccessibleName('Find text')
        self.replacement=qt.QLineEdit();self.replacement.setPlaceholderText('Replace with');self.replacement.setAccessibleName('Replacement text')
        self.previous=qt.QToolButton();self.previous.setText('Previous');self.previous.clicked.connect(lambda:self.find(-1))
        self.next=qt.QToolButton();self.next.setText('Next');self.next.clicked.connect(self.find)
        self.replace=qt.QPushButton('Replace');self.replace.clicked.connect(self.replace_one)
        self.replace_all_button=qt.QPushButton('Replace All');self.replace_all_button.clicked.connect(self.replace_all)
        close=qt.QToolButton();close.setText('×');close.setToolTip('Close search');close.clicked.connect(self.close_panel)
        for widget in (self.query,self.replacement,self.previous,self.next,self.replace,self.replace_all_button,close):row.addWidget(widget)
        layout.addLayout(row);options=qt.QHBoxLayout()
        self.case=qt.QCheckBox('Match case');self.whole=qt.QCheckBox('Whole word');self.regex=qt.QCheckBox('Regular expression');self.wrap=qt.QCheckBox('Wrap');self.wrap.setChecked(True)
        self.selection=qt.QCheckBox('In selection');self.selection.toggled.connect(self._selection_changed)
        self.summary=qt.QLabel();self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        for widget in (self.case,self.whole,self.regex,self.wrap,self.selection):options.addWidget(widget)
        options.addWidget(self.summary,1);layout.addLayout(options)
        self.task=OperationProgress(self);self.task.completed.connect(self._completed);layout.addWidget(self.task)
        self.timer=qt.QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(150);self.timer.timeout.connect(self._search)
        for field in (self.query,self.replacement):field.textChanged.connect(self.schedule)
        for field in (self.case,self.whole,self.regex):field.toggled.connect(self.schedule)
        self.query.returnPressed.connect(self.find);self.replacement.returnPressed.connect(self.replace_one)
        self.hide()

    @property
    def busy(self):return self.task.busy
    def set_editor(self,editor):
        if self.editor is editor:return
        if self.editor:
            self.editor.textChanged.disconnect(self.schedule);self.editor.cursorPositionChanged.disconnect(self._count)
            self.editor.search_selections=[];self.editor.highlight_cursor()
        self._generation+=1;self.editor=editor;self.scope=None;self.selection.setChecked(False)
        if editor:editor.textChanged.connect(self.schedule);editor.cursorPositionChanged.connect(self._count)
        self.schedule()
    def open(self,replace=False):
        if self.editor and self.editor.textCursor().hasSelection() and not self.selection.isChecked():
            selected=self.editor.textCursor().selectedText()
            if '\u2029' not in selected and len(selected)<2048:self.query.setText(selected)
        self.replacement.setVisible(replace);self.replace.setVisible(replace);self.replace_all_button.setVisible(replace)
        self.show();self.query.setFocus();self.query.selectAll();self.schedule()
    def close_panel(self):
        self._generation+=1
        self.timer.stop();self.hide();self.task.request_cancel();self._pending=False
        if self.editor:self.editor.search_selections=[];self.editor.highlight_cursor();self.editor.setFocus()
    def _selection_changed(self,enabled):
        self.scope=qt.QTextCursor(self.editor.textCursor()) if enabled and self.editor else None
        if enabled and (self.scope is None or not self.scope.hasSelection()):self.selection.setChecked(False)
        self.schedule()
    def schedule(self,*args):
        self._generation+=1;self.matches=[];self.replace.setEnabled(False);self.replace_all_button.setEnabled(False)
        if self.editor:self.editor.search_selections=[];self.editor.highlight_cursor()
        if self.isVisible():self.timer.start()
    def _search(self):
        if self.editor is None or not self.isVisible():return
        if self.task.busy:self._pending=True;self.task.request_cancel();return
        text=self.editor.toPlainText();query=self.query.text();replacement=self.replacement.text()
        scope=(self.scope.selectionStart(),self.scope.selectionEnd()) if self.scope and self.scope.hasSelection() else None
        self._signature=(self._generation,self.editor.document().revision())
        options=dict(case=self.case.isChecked(),whole=self.whole.isChecked(),regex=self.regex.isChecked(),scope=scope)
        self.summary.setText('Searching…')
        self.task.start(lambda report,cancelled:find_matches(text,query,replacement,cancelled=cancelled,**options),show_progress=False)
    def _completed(self,result,error):
        if self.editor and self._signature==(self._generation,self.editor.document().revision()):
            if error:self.summary.setText('Invalid search: '+error)
            else:
                self.matches,self.truncated=result;self._highlight();self._count()
                self.replace.setEnabled(bool(self.matches));self.replace_all_button.setEnabled(bool(self.matches) and not self.truncated)
        self.idle.emit()
        if self._pending:self._pending=False;self.timer.start(0)
    def _highlight(self):
        if self.editor.document().characterCount()>1024*1024:return
        selections=[]
        for match in self.matches[:1000]:
            selection=qt.QTextEdit.ExtraSelection();selection.cursor=qt.QTextCursor(self.editor.document());selection.cursor.setPosition(match.start)
            selection.cursor.setPosition(match.start+match.length,qt.QTextCursor.MoveMode.KeepAnchor)
            color=self.palette().color(qt.QPalette.ColorRole.Highlight);color.setAlpha(70);selection.format.setBackground(color);selections.append(selection)
        self.editor.search_selections=selections;self.editor.highlight_cursor()
    def _count(self):
        current=0
        if self.editor:
            cursor=self.editor.textCursor()
            current=next((index+1 for index,match in enumerate(self.matches) if match.start==cursor.selectionStart() and match.length==cursor.selectionEnd()-cursor.selectionStart()),0)
        self.summary.setText(f'{current} / {len(self.matches):,}'+('+' if self.truncated else '')+' matches')
    def find(self,direction=1):
        direction=-1 if direction==-1 else 1
        if not self.editor:return
        if not self.isVisible():self.open()
        if not self.matches:
            self._search();return
        cursor=self.editor.textCursor();start=cursor.selectionStart();end=cursor.selectionEnd()
        if direction>0:
            match=next((m for m in self.matches if m.start>=end and not (m.length==0 and m.start==start and cursor.hasSelection()==False)),None)
        else:match=next((m for m in reversed(self.matches) if m.start<start),None)
        if match is None:
            if not self.wrap.isChecked():self.summary.setText('End of search; wrap is off.');return
            match=self.matches[0 if direction>0 else -1]
        cursor.setPosition(match.start);cursor.setPosition(match.start+match.length,qt.QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor);self.editor.ensureCursorVisible();self._count()
    def replace_one(self):
        if not self.editor or self.editor.isReadOnly() or not self.matches:return
        cursor=self.editor.textCursor()
        match=next((m for m in self.matches if m.start==cursor.selectionStart() and m.start+m.length==cursor.selectionEnd()),None)
        if match is None:self.find();return
        cursor.beginEditBlock();cursor.insertText(match.replacement);cursor.endEditBlock();self.editor.setTextCursor(cursor)
    def replace_all(self):
        if not self.editor or self.editor.isReadOnly() or self.truncated or not self.matches:return
        cursor=qt.QTextCursor(self.editor.document());cursor.beginEditBlock()
        for match in reversed(self.matches):
            cursor.setPosition(match.start);cursor.setPosition(match.start+match.length,qt.QTextCursor.MoveMode.KeepAnchor);cursor.insertText(match.replacement)
        cursor.endEditBlock()
    def prepare_close(self):
        self.timer.stop();self._pending=False
        if self.task.busy:self.task.request_cancel();return False
        return True
