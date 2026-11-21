"""Small Blade overlay delegating HTML/PHP to established Pygments grammars.

Qt's delegating-lexer fallback operates per line; multiline Blade expressions
are intentionally not a full template parser.
"""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

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
