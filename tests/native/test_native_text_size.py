"""Explicit text-size callbacks preserve drafts and retire queued reflow."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock
from commonUtils.ui.native.text_size import TextSizeBinding


class Widget:
    def __init__(self):
        self.style = NS(font_size=20)
        self._impl = NS()
        self.value = 'Unsaved draft'
        self.on_webview_load = AsyncMock()
        self.evaluate_javascript = AsyncMock()


class TextSizeTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_limits_commit_once_cancel_and_disposal(self):
        widget, current, saves = Widget(), [20], []
        def save(size):
            saves.append(size)
            current[0] = size
        binding = TextSizeBinding(widget, loop=asyncio.get_running_loop(),
                                  get_size=lambda: current[0], save_size=save, minimum=10, maximum=40)
        binding.gesture('begin')
        binding.gesture('change', 100)
        self.assertEqual(widget.style.font_size, 40)
        self.assertFalse(saves)
        binding.gesture('end')
        self.assertEqual(saves, [40])
        binding.gesture('begin')
        binding.gesture('change', .01)
        self.assertEqual(widget.style.font_size, 10)
        binding.gesture('cancel')
        self.assertEqual(widget.style.font_size, 40)
        self.assertEqual(saves, [40])
        binding.dispose()
        binding.apply(20)
        self.assertEqual(widget.style.font_size, 40)
        self.assertEqual(widget.value, 'Unsaved draft')

    async def test_web_reflow_preserves_content_and_restores_load_handler(self):
        widget = Widget()
        old_handler = widget.on_webview_load
        active = [True]
        binding = TextSizeBinding(widget, loop=asyncio.get_running_loop(), get_size=lambda: 24,
                                  web=True, alignment=lambda: 'justify', alive=lambda: active[0])
        binding.attach_load()
        await widget.on_webview_load(widget)
        await asyncio.sleep(0)
        old_handler.assert_awaited_once()
        self.assertIn("'24px'", widget.evaluate_javascript.call_args.args[0])
        self.assertIn("'--text-align','justify'", widget.evaluate_javascript.call_args.args[0])
        widget.evaluate_javascript.reset_mock()
        binding.apply(30)
        active[0] = False
        await asyncio.sleep(0)
        widget.evaluate_javascript.assert_not_awaited()
        binding.dispose()
        self.assertIs(widget.on_webview_load, old_handler)
        self.assertEqual(widget.value, 'Unsaved draft')

    async def test_save_failure_reports_then_restores_current_size(self):
        widget, errors = Widget(), []
        def fail(size):
            raise OSError('read only')
        binding = TextSizeBinding(widget, loop=asyncio.get_running_loop(), get_size=lambda: 20,
                                  save_size=fail, on_error=errors.append)
        binding.gesture('begin')
        binding.gesture('change', 1.5)
        binding.gesture('end')
        self.assertEqual(str(errors[0]), 'read only')
        self.assertEqual(widget.style.font_size, 20)
        binding.dispose()
