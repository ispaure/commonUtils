"""Verify Qt Markdown playback and highlight use the rendered coordinate map."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from unittest.mock import patch

from commonUtils.tests.appearance.test_read_aloud import SilentEngine
from commonUtils.tests.markdown.test_markdown_speech import MIXED
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown.speech import prepare_document
from commonUtils.ui.markdown.viewer import MarkdownViewer


class MarkdownSpeechQtTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.viewer = MarkdownViewer()
        self.addCleanup(self.viewer.deleteLater)
        self.addCleanup(self.viewer.close)
        self.viewer._render_source(MIXED)
        self.viewer.show()

    def test_mixed_visible_rules_and_selected_highlight_reach_engine(self):
        viewer = self.viewer
        prepared = prepare_document(viewer.browser)
        for text in ('😀 Heading', 'image.jpg', 'Technology', 'Visible caption.', 'Closed',
                     'Header Next\n\nOne Two', 'checked Complete', 'unchecked Pending',
                     'Footnote One footnote only.', '<!-- visible in code -->',
                     '<!-- literal -->', 'Unresolved note'):
            self.assertIn(text, prepared.text)
        for hidden in ('Frontmatter secret', 'snoopy-died', 'image-target.jpg', 'Collapsed secret',
                       'Hidden HTML', 'hidden Obsidian', r'\frac', 'hidden query', 'dv.io'):
            self.assertNotIn(hidden, prepared.text)
        selection = viewer.browser.document().find('😀 Heading')
        viewer.browser.setTextCursor(selection)
        speech = viewer.speech
        speech.engine_factory = SilentEngine
        speech.show()
        with patch('commonUtils.ui.readers.read_aloud.passage_language', return_value=''):
            speech.start()
        self.assertEqual(speech.engine.spoken[-1], '😀 Heading')
        speech.engine.sayingWord.emit('Heading', 0, 3, 7)
        selections = viewer.browser.extraSelections()
        highlight = selections[-1].cursor
        self.assertEqual(highlight.selectedText(), 'Heading')
        self.assertEqual(highlight.selectionStart(), selection.selectionStart() + 3)
        speech.stop()
