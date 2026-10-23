"""Standalone CodeInput consumes portable language state without Logistics."""
import asyncio
import importlib.util
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('TOGA_BACKEND', 'toga_dummy')


@unittest.skipUnless(importlib.util.find_spec('toga'), 'Optional Toga backend is not installed')
class NativeCodeLanguageTests(unittest.TestCase):
    def setUp(self):
        import toga
        from commonUtils.ui.native.code_input import CodeInput
        self.app = toga.App('Language tests', 'org.example.language-tests')
        self.loop = asyncio.new_event_loop()
        self.changes = []
        self.editor = CodeInput(loop=self.loop, filename='sample.py',
                                on_change=lambda widget: self.changes.append(widget.value))
        self.addCleanup(self.loop.close)
        self.addCleanup(self.editor.dispose)

    def test_automatic_manual_plain_text_and_rename_preserve_source(self):
        from commonUtils.formats.code_language import LanguageSelection
        editor = self.editor
        self.assertIsInstance(editor.language_selection, LanguageSelection)
        editor.value = 'print(1)'
        count = len(self.changes)
        self.assertEqual(editor.language, 'python')
        self.assertIsNone(editor.language_override)
        editor.set_language('text')
        editor.set_filename('renamed.json')
        self.assertEqual(editor.language, 'text')
        self.assertEqual(editor.language_selection.detected_id, 'json')
        editor.set_language(None)
        self.assertEqual(editor.language, 'json')
        self.assertEqual(editor.value, 'print(1)')
        self.assertEqual(len(self.changes), count)

    def test_shebang_edits_and_existing_override_attribute_use_shared_state(self):
        editor = self.editor
        editor.set_filename('')
        editor.value = '#!/usr/bin/env python\nprint(1)'
        self.assertEqual(editor.language, 'python')
        editor.language_override = 'json'
        editor.value = '#!/bin/sh\necho hi'
        self.assertEqual(editor.language, 'json')
        editor.set_language(None)
        self.assertEqual(editor.language, 'bash')

    def test_repeated_source_changes_do_not_repeat_detection_for_the_same_prefix(self):
        editor = self.editor
        with patch('commonUtils.formats.code_language.detect_language', return_value='python') as detect:
            editor.value = 'x' * 300
            editor.value = 'x' * 256 + 'new suffix'
            detect.assert_called_once_with('sample.py', 'x' * 256)

    def test_language_change_rejects_an_inflight_highlight_without_changing_text(self):
        editor = self.editor
        editor.value = 'print(1)'
        async def check():
            entered, release = asyncio.Event(), asyncio.Event()
            async def spans(*args, **kwargs):
                entered.set()
                await release.wait()
                return 'python', ()
            with patch('commonUtils.ui.native.code_input.asyncio.to_thread', side_effect=spans):
                task = asyncio.create_task(editor.highlight())
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    editor.set_language('json')
                finally:
                    release.set()
                    await task
            self.assertEqual(editor.language, 'json')
            self.assertEqual(editor.value, 'print(1)')
            self.assertFalse(editor.applying)
        self.loop.run_until_complete(check())


if __name__ == '__main__':
    unittest.main()
