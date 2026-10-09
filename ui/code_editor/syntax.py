"""Incremental Qt syntax formatting backed by optional Pygments definitions.

RegexLexer states are carried across QTextBlocks, so ordinary edits rehighlight
only affected blocks. Extended/delegating lexers use bounded per-block fallback.
No source is executed. Long blocks and large documents opt out of highlighting.

The state runner adapts Pygments' RegexLexer algorithm (BSD-2-Clause; see
PYGMENTS_LICENSE.txt). Its compiled-rule adapter is tested with pinned 2.19.2.
"""
from .. import pyside as qt

LANGUAGES=(('Plain Text','text'),('Python','python'),('Shell','bash'),('Windows Batch','batch'),
           ('PowerShell','powershell'),('Markdown','markdown'),('JSON','json'),('XML','xml'),
           ('HTML','html'),('YAML','yaml'),('TOML','toml'),('INI / Configuration','ini'),
           ('JavaScript','javascript'),('TypeScript','typescript'),('C','c'),('C++','cpp'),
           ('CSS','css'),('SQL','sql'),('C#','csharp'),('Java','java'),('Rust','rust'),('Go','go'))
COMMENT_PREFIX={'bash':'#','python':'#','powershell':'#','yaml':'#','toml':'#','ini':';',
                'batch':'REM','javascript':'//','typescript':'//','c':'//','cpp':'//','csharp':'//',
                'java':'//','rust':'//','go':'//','sql':'--'}


def detect_language(path,text=''):
    try:
        from pygments.lexers import get_lexer_for_filename,get_lexer_by_name
        if path:
            name=str(path)
            if name.endswith(('.command','.zsh','.bash')):return 'bash'
            if name.endswith(('.env','.gitignore','.editorconfig','.conf','.cfg')):return 'ini'
            if name.endswith('.csv'):return 'text'
            lexer=get_lexer_for_filename(name,stripnl=False,ensurenl=False)
            if lexer.aliases:return lexer.aliases[0]
    except (ImportError,ValueError):pass
    first=text.split('\n',1)[0]
    if first.startswith('#!'):
        if 'python' in first:return 'python'
        if any(shell in first for shell in ('sh','bash','zsh')):return 'bash'
    return 'text'


def regex_tokens(lexer,text,stack):
    """Return tokens and final state for one bounded logical line."""
    from pygments.token import _TokenType,Whitespace,Error
    states=list(stack);position=0;result=[];steps=0
    while position<len(text) and steps<20000:
        steps+=1
        for match_rule,action,new_state in lexer._tokens[states[-1]]:
            match=match_rule(text,position)
            if not match:continue
            if action is not None:
                if isinstance(action,_TokenType):result.append((position,action,match.group()))
                else:result.extend(action(lexer,match))
            before=tuple(states);previous=position;position=match.end()
            if isinstance(new_state,tuple):
                for state in new_state:
                    if state=='#pop':
                        if len(states)>1:states.pop()
                    elif state=='#push':states.append(states[-1])
                    else:states.append(state)
            elif isinstance(new_state,int):
                if abs(new_state)>=len(states):states=states[:1]
                else:del states[new_state:]
            elif new_state=='#push':states.append(states[-1])
            if previous==position and before==tuple(states):position+=1
            break
        else:
            if text[position]=='\n':states=['root'];kind=Whitespace
            else:kind=Error
            result.append((position,kind,text[position]));position+=1
    return result,tuple(states)


class SyntaxHighlighter(qt.QSyntaxHighlighter):
    def __init__(self,editor,language='text'):
        super().__init__(editor.document());self.editor=editor;self.language='text';self.lexer=None;self.style=None
        self.formats={};self.states={('root',):0};self.reverse_states={0:('root',)}
        self.theme_timer=qt.QTimer(editor);self.theme_timer.setSingleShot(True);self.theme_timer.timeout.connect(self.refresh_theme)
        editor.installEventFilter(self);self.configure(language)
    def configure(self,language):
        self.language=language;self.lexer=None;self.formats.clear();self.states={('root',):0};self.reverse_states={0:('root',)}
        try:
            from pygments.lexers import get_lexer_by_name
            if language!='text':self.lexer=get_lexer_by_name(language,stripnl=False,ensurenl=False)
        except (ImportError,ValueError):self.language='text'
        self.editor.comment_prefix=COMMENT_PREFIX.get(self.language)
        self.refresh_theme()
    def eventFilter(self,watched,event):
        if event.type()==qt.QEvent.Type.PaletteChange:self.theme_timer.start(0)
        return False
    def refresh_theme(self):
        try:
            from pygments.styles import get_style_by_name
            dark=self.editor.palette().color(qt.QPalette.ColorRole.Base).lightness()<128
            self.style=get_style_by_name('native' if dark else 'default');self.formats.clear();self.rehighlight()
        except ImportError:pass
    def token_format(self,token):
        if token not in self.formats:
            spec=self.style.style_for_token(token);fmt=qt.QTextCharFormat()
            if spec['color']:fmt.setForeground(qt.QColor('#'+spec['color']))
            if spec['bold']:fmt.setFontWeight(qt.QFont.Weight.Bold)
            fmt.setFontItalic(spec['italic']);self.formats[token]=fmt
        return self.formats[token]
    def highlightBlock(self,text):
        if self.lexer is None or self.style is None or len(text)>20000 or self.document().characterCount()>1024*1024:
            self.setCurrentBlockState(0);return
        from pygments.lexer import RegexLexer,ExtendedRegexLexer
        try:
            if isinstance(self.lexer,RegexLexer) and not isinstance(self.lexer,ExtendedRegexLexer):
                stack=self.reverse_states.get(self.previousBlockState(),('root',))
                tokens,stack=regex_tokens(self.lexer,text+'\n',stack)
                if stack not in self.states:
                    identity=len(self.states);self.states[stack]=identity;self.reverse_states[identity]=stack
                self.setCurrentBlockState(self.states[stack])
            else:
                tokens=list(self.lexer.get_tokens_unprocessed(text+'\n'));self.setCurrentBlockState(0)
            positions=[0]
            for char in text:positions.append(positions[-1]+(2 if ord(char)>65535 else 1))
            for offset,kind,value in tokens:
                if offset>=len(text):continue
                end=min(len(text),offset+len(value));self.setFormat(positions[offset],positions[end]-positions[offset],self.token_format(kind))
        except (ValueError,KeyError,TypeError,IndexError):
            self.setCurrentBlockState(0)  # Unknown/custom lexer behavior must not break editing.
