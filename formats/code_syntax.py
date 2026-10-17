"""Toolkit-independent language choices shared by desktop and native editors."""

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
