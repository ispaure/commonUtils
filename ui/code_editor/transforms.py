"""Pure text transformations; callers own selection and undo policy."""


def transform_lines(text, command, width=4, start=1):
    final = text.endswith("\n")
    lines = text[:-1].split("\n") if final else text.split("\n")
    if command == "sort":
        lines.sort()
    elif command == "sort_reverse":
        lines.sort(reverse=True)
    elif command == "unique":
        lines = list(dict.fromkeys(lines))
    elif command == "trim":
        lines = [line.rstrip(" \t") for line in lines]
    elif command == "tabs_to_spaces":
        lines = [line.expandtabs(width) for line in lines]
    elif command == "spaces_to_tabs":
        converted = []
        for line in lines:
            count = len(line) - len(line.lstrip(" "))
            converted.append("\t" * (count // width) + " " * (count % width) + line[count:])
        lines = converted
    elif command == "number":
        lines = [f"{index}: {line}" for index, line in enumerate(lines, start)]
    else:
        raise ValueError(f"Unknown line transformation: {command}")
    return "\n".join(lines) + ("\n" if final else "")


class TransformCommands:
    def transform(self, command, *, start=1):
        if self.isReadOnly():
            return
        cursor = self.textCursor()
        if command in ("upper", "lower", "title"):
            if not cursor.hasSelection():
                cursor.select(cursor.SelectionType.WordUnderCursor)
            source = cursor.selectedText().replace("\u2029", "\n")
            result = getattr(source, command)()
        else:
            if cursor.hasSelection():
                blocks = self.selected_blocks()
                cursor.setPosition(blocks[0].position())
                cursor.setPosition(blocks[-1].position() + blocks[-1].length() - 1,
                                   cursor.MoveMode.KeepAnchor)
            else:
                cursor.select(cursor.SelectionType.Document)
            source = cursor.selectedText().replace("\u2029", "\n")
            result = transform_lines(source, command, self.indent_width, start)
        if result == source:
            return
        origin = cursor.selectionStart()
        cursor.beginEditBlock()
        cursor.insertText(result)
        cursor.endEditBlock()
        cursor.setPosition(origin, cursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
