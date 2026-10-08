"""Markdown text files open in the shared reader when activated in a browser."""
from .txtType import TXTFile
from .registry import register_file_type


class MarkdownFile(TXTFile):
    def browser_activate(self, context):
        from ..ui.markdown import open_markdown
        open_markdown(self.path, parent=context.widget.window())
        return True


register_file_type(MarkdownFile, ('md', 'markdown'), priority=-100)
