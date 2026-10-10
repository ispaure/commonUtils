"""Bounded explicit structured-text validation and conservative formatting."""
import json
import re
from xml.dom import minidom, Node

MAX_FORMAT_CHARS = 1024 * 1024


def validate_text(text, language):
    if len(text) > MAX_FORMAT_CHARS:
        raise ValueError("Formatting and validation are limited to 1 MiB of text.")
    if language == "json":
        def reject(value):
            raise ValueError(f"Invalid JSON constant: {value}")
        json.loads(text, parse_constant=reject)
    elif language == "xml":
        if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.I):
            raise ValueError("XML DTDs and entity declarations are not supported.")
        document = minidom.parseString(text)
        document.unlink()
    else:
        raise ValueError("Choose JSON or XML.")


def format_text(text, language, width=4):
    validate_text(text, language)
    final = text.endswith("\n")
    if language == "json":
        # Preserve all tokens, especially numeric precision and duplicate keys.
        tokens = re.findall(r'"(?:[^"\\]|\\.)*"|[^\s]', text)
        output, depth = [], 0
        for index, token in enumerate(tokens):
            previous = tokens[index - 1] if index else ""
            following = tokens[index + 1] if index + 1 < len(tokens) else ""
            if token in ("{", "["):
                output.append(token)
                depth += 1
                if following not in ("}", "]"):
                    output.append("\n" + " " * (depth * width))
            elif token in ("}", "]"):
                depth -= 1
                if previous not in ("{", "["):
                    output.append("\n" + " " * (depth * width))
                output.append(token)
            elif token == ",":
                output.append(",\n" + " " * (depth * width))
            elif token == ":":
                output.append(": ")
            else:
                output.append(token)
        result = "".join(output)
    else:
        document = minidom.parseString(text)
        try:
            def clean(node):
                if node.nodeType == Node.ELEMENT_NODE and node.getAttribute("xml:space") == "preserve":
                    raise ValueError("XML with xml:space='preserve' can be validated but is not reformatted.")
                elements = any(child.nodeType == Node.ELEMENT_NODE for child in node.childNodes)
                content = any(child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE)
                              and child.data.strip() for child in node.childNodes)
                if elements and content:
                    raise ValueError("Mixed-content XML can be validated but is not reformatted.")
                for child in list(node.childNodes):
                    if elements and child.nodeType == Node.TEXT_NODE and not child.data.strip():
                        node.removeChild(child)
                        child.unlink()
                    elif child.nodeType == Node.ELEMENT_NODE:
                        clean(child)
            clean(document)
            result = document.toprettyxml(indent=" " * width).rstrip("\n")
            if not text.lstrip().startswith("<?xml"):
                result = result.split("\n", 1)[1]
        finally:
            document.unlink()
    return result + ("\n" if final else "")
