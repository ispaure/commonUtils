"""Markdown text files open in the shared reader when activated in a browser."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from ..txtType import TXTFile
from ..registry import register_file_type


class MarkdownFile(TXTFile):
    def browser_activate(self, context):
        from ...ui.markdown import open_markdown
        open_markdown(self.path, parent=context.widget.window())
        return True


register_file_type(MarkdownFile, ('md', 'markdown'), priority=-100)
