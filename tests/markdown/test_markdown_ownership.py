"""Document baselines and independently wired Markdown editing components."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import unittest

from commonUtils.ui.markdown.session import MarkdownDocumentState
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown.formatted import FormattedEditing
from commonUtils.ui.markdown.live_edit import SourceMarkdownEdit, FormattedMarkdownEdit
from commonUtils.ui.markdown import MarkdownViewer


class DocumentOwnershipTests(unittest.TestCase):
    def test_new_document_clears_saved_and_formatted_baselines(self):
        draft = MarkdownDocumentState()
        original = b'\xef\xbb\xbf# Exact\r\n'
        draft.load(Path('old.md'), original)
        draft.rich_source, draft.rich_snapshot = '# Exact\n', '# Normalized\n'
        self.assertEqual(draft.capture('# Exact\n', False), original)
        draft.new()
        self.assertIsNone(draft.loaded_path)
        self.assertIsNone(draft.source_bytes)
        self.assertIsNone(draft.rich_source)
        self.assertIsNone(draft.rich_snapshot)
        self.assertEqual(draft.capture('# New\n', True), b'# New\n')

    def test_loading_another_document_clears_rich_baseline_without_sharing_state(self):
        first, other = MarkdownDocumentState(), MarkdownDocumentState()
        first.rich_snapshot = 'old body'
        first.load(Path('next.md'), b'new body')
        self.assertIsNone(first.rich_snapshot)
        self.assertIsNone(other.source_bytes)
        self.assertEqual(first.source_bytes, b'new body')

    def test_pending_save_is_owned_by_the_document(self):
        draft = MarkdownDocumentState()
        self.assertFalse(draft.begin_save(False))
        self.assertFalse(draft.save_pending)
        self.assertTrue(draft.begin_save(True))
        self.assertFalse(draft.begin_save(True))
        draft.save_pending = False
        self.assertTrue(draft.begin_save(True))


class FormattedOwnershipTests(QtTestCase):
    def test_widget_modified_signal_respects_host_dirty_state_override(self):
        class HostOwnedDirtyState(MarkdownViewer):
            @property
            def is_modified(self):
                return False
        viewer = HostOwnedDirtyState(allow_edit=True)
        self.addCleanup(viewer.deleteLater)
        changes = []
        viewer.modified_changed.connect(changes.append)
        viewer.formatted_editor.insertPlainText('edited')
        self.assertTrue(changes)
        self.assertFalse(changes[-1])

    def component(self, text):
        # Construct just the synchronization component. It must not require a
        # viewer, a wiki, toolbar fields, reading state or a storage provider.
        parent = qt.QWidget()
        self.addCleanup(parent.deleteLater)
        source, editor = SourceMarkdownEdit(parent), FormattedMarkdownEdit(parent)
        mode = qt.QComboBox(parent)
        mode.addItem('Formatted', 'formatted')
        mode.addItem('Source', 'source')
        source.setPlainText(text)
        source.document().setModified(False)
        messages, modifications = [], []
        session = MarkdownDocumentState()
        sync = FormattedEditing(source, editor, mode, session,
            set_mode=lambda value: mode.setCurrentIndex(mode.findData(value)),
            status=messages.append, modified=modifications.append)
        return sync, session, messages, modifications

    def test_round_trip_without_edits_keeps_exact_source_and_undo_history(self):
        original = '---\ntitle: Exact\n---\n\n# Heading\n\n**Body**\n'
        sync, session, messages, modified = self.component(original)
        sync.load()
        self.assertEqual(sync.text(), original)
        self.assertFalse(sync.pending())
        self.assertFalse(sync.source.document().isModified())
        self.assertFalse(sync.source.document().isUndoAvailable())

    def test_real_rich_edits_preserve_yaml_and_sync_as_one_source_undo_step(self):
        original = '---\ntitle: Exact\n---\n\nBody\n'
        sync, session, messages, modified = self.component(original)
        sync.load()
        sync.editor.moveCursor(qt.QTextCursor.MoveOperation.End)
        sync.editor.insertPlainText(' changed')
        self.assertTrue(sync.pending())
        self.assertTrue(sync.text().startswith('---\ntitle: Exact\n---\n'))
        self.assertIn('changed', sync.source.toPlainText())
        sync.source.undo()
        self.assertEqual(sync.source.toPlainText(), original)

    def test_unclosed_properties_fall_back_without_mutating_source(self):
        original = '---\ntitle: Unclosed\n\nBody'
        sync, session, messages, modified = self.component(original)
        sync.load()
        self.assertEqual(sync.mode.currentData(), 'source')
        self.assertEqual(sync.source.toPlainText(), original)
        self.assertIsNone(session.rich_snapshot)
        self.assertTrue(messages)
