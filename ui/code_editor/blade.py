"""Small Blade overlay delegating HTML/PHP to established Pygments grammars.

Qt's delegating-lexer fallback operates per line; multiline Blade expressions
are intentionally not a full template parser.
"""
from pygments.lexer import DelegatingLexer, RegexLexer, bygroups, using
from pygments.lexers.templates import HtmlPhpLexer
from pygments.lexers.php import PhpLexer
from pygments.token import Comment, Keyword, Other, String


class BladeDirectives(RegexLexer):
    tokens = {'root': [
        (r'\{\{--.*?--\}\}', Comment),
        (r'(\{!!)(.*?)(!!\})', bygroups(String.Interpol, using(PhpLexer, startinline=True), String.Interpol)),
        (r'(\{\{)(.*?)(\}\})', bygroups(String.Interpol, using(PhpLexer, startinline=True), String.Interpol)),
        (r'@@\w+', Other),
        (r'@[a-zA-Z_]\w*', Keyword),
        (r'[^@{]+|.', Other),
    ]}


class BladeLexer(DelegatingLexer):
    def __init__(self, **options):
        super().__init__(HtmlPhpLexer, BladeDirectives, **options)
