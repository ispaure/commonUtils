"""Toolkit-independent language choices shared by desktop and native editors."""

from functools import lru_cache


@lru_cache(maxsize=2)
def syntax_style(dark=False):
    """Shared restrained syntax accents; unstyled tokens inherit host colors.

    Pygments remains optional until highlighting is requested. No foreground or
    background is supplied for ordinary text, module paths or function names.
    """
    from pygments.style import Style
    from pygments.token import Token, Text, Whitespace, Error, Comment, Keyword
    from pygments.token import Name, String, Number, Operator, Generic

    keyword = '#c78962' if dark else '#2449c4'
    string = '#70a875' if dark else '#237c32'
    number = '#739bc4' if dark else '#235fc1'
    builtin = '#ac91c7' if dark else '#6042a6'
    comment = '#858990' if dark else '#777c84'

    class EditorStyle(Style):
        background_color = None
        styles = {
            Token: '', Text: '', Whitespace: '', Error: '',
            Comment: 'italic ' + comment,
            Comment.Preproc: 'noitalic ' + keyword,
            Keyword: keyword,
            Operator.Word: keyword,
            String: string,
            Number: number,
            Name: '',
            Name.Builtin: builtin,
            Name.Exception: builtin,
            Name.Builtin.Pseudo: 'noinherit',
            Name.Function: '', Name.Class: '', Name.Namespace: '',
            Name.Decorator: '#b6a16b' if dark else '#88651c',
            Name.Tag: keyword,
            Name.Attribute: builtin,
            Generic.Heading: keyword,
            Generic.Subheading: keyword,
            Generic.Emph: 'italic',
            Generic.Strong: 'bold',
            Generic.Deleted: '#cf7777' if dark else '#af3434',
            Generic.Inserted: string,
        }

    return EditorStyle


LANGUAGES = (
    ("Plain Text", "text"),
    ("Python", "python"),
    ("PHP / HTML", "html+php"),
    ("Laravel Blade", "blade"),
    ("Shell", "bash"),
    ("Windows Batch", "batch"),
    ("PowerShell", "powershell"),
    ("Markdown", "markdown"),
    ("JSON", "json"),
    ("XML", "xml"),
    ("HTML", "html"),
    ("YAML", "yaml"),
    ("TOML", "toml"),
    ("INI / Configuration", "ini"),
    ("JavaScript", "javascript"),
    ("TypeScript", "typescript"),
    ("C", "c"),
    ("C++", "cpp"),
    ("CSS", "css"),
    ("SQL", "sql"),
    ("C#", "csharp"),
    ("Java", "java"),
    ("Rust", "rust"),
    ("Go", "go"),
)
COMMENT_PREFIX = {
    "bash": "#",
    "python": "#",
    "php": "//",
    "html+php": "//",
    "powershell": "#",
    "yaml": "#",
    "toml": "#",
    "ini": ";",
    "batch": "REM",
    "javascript": "//",
    "typescript": "//",
    "c": "//",
    "cpp": "//",
    "csharp": "//",
    "java": "//",
    "rust": "//",
    "go": "//",
    "sql": "--",
}


def detect_language(path, text=""):
    name = str(path).lower() if path else ""
    if name.endswith(".blade.php"):
        return "blade"
    if name.endswith(".php"):
        return "html+php"
    if name.endswith((".py", ".pyi")):
        return "python"
    # The common editor formats are unambiguous. Avoid loading/scanning the
    # Pygments filename registry on the UI thread merely to open a local note.
    for suffixes, language in (
        ((".md", ".markdown"), "markdown"), ((".txt",), "text"),
        ((".json",), "json"), ((".yaml", ".yml"), "yaml"),
        ((".toml",), "toml"), ((".ini",), "ini"),
    ):
        if name.endswith(suffixes):
            return language
    try:
        from pygments.lexers import get_lexer_for_filename

        if path:
            name = str(path).lower()
            if name.endswith((".command", ".zsh", ".bash")):
                return "bash"
            if name.endswith((".env", ".gitignore", ".editorconfig", ".conf", ".cfg")):
                return "ini"
            if name.endswith(".csv"):
                return "text"
            lexer = get_lexer_for_filename(name, stripnl=False, ensurenl=False)
            if lexer.aliases:
                return lexer.aliases[0]
    except (ImportError, ValueError):
        pass
    first = text.split("\n", 1)[0]
    if first.startswith("#!"):
        if "python" in first:
            return "python"
        if any(shell in first for shell in ("sh", "bash", "zsh")):
            return "bash"
    return "text"


# Common source/configuration names for hosts that offer a text-file picker.
SOURCE_EXTENSIONS = ('.txt', '.md', '.markdown', '.ini', '.py', '.pyi', '.json',
    '.yaml', '.yml', '.toml', '.xml', '.html', '.htm', '.css', '.js', '.mjs',
    '.jsx', '.ts', '.tsx', '.sh', '.bash', '.zsh', '.command', '.ps1', '.bat',
    '.cmd', '.c', '.h', '.cpp', '.hpp', '.cs', '.java', '.rs', '.go', '.php',
    '.sql', '.cfg', '.conf', '.env')
