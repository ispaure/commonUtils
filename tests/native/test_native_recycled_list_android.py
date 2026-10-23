"""Native list appearance follows Android theme and high-contrast changes."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

LIGHT = dict(text='#111111', muted='#333333', surface='#ffffff', hover='#eeeeee', accent='#0000ff', border='#555555')
DARK = dict(text='#eeeeee', muted='#bbbbbb', surface='#111111', hover='#333333', accent='#aaaaff', border='#999999')
EINK = dict(text='#000000', muted='#000000', surface='#ffffff', hover='#ffffff', accent='#000000', border='#000000')


class AndroidFileListAppearanceTests(unittest.TestCase):
    def test_metrics_and_source_generations_reach_native_adapter(self):
        native = Mock()
        factory = Mock(return_value=native)
        factory.Listener = object
        modules = {
            'toga_android.widgets.base': NS(Widget=object),
            'java': NS(dynamic_proxy=lambda cls: object),
            'io.github.ispaure.commonutils': NS(FileListView=factory),
        }
        path = Path(__file__).parents[2] / 'ui/native/recycled_list_android.py'
        spec = importlib.util.spec_from_file_location('commonUtils.ui.native._android_generation_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(module)
            impl = module.AndroidFileList()
            impl._native_activity = object()
            current = NS(title='Current', subtitle='', folder=False, thumbnail=False)
            impl.interface = NS(appearance=NS(row_height=56, body_text=18, caption_text=14,
                icon_size=32, icon=lambda folder: None), data=[current],
                on_select=Mock(), row_visible=Mock(), on_primary_action=Mock())
            impl.refresh_palette = Mock()
            impl.create()
            native.setMetrics.assert_called_once_with(56, 18, 14, 32)
            old_generation = impl.generation
            impl.change_source(impl.interface.data)
            native.setIcons.assert_called_once_with(None, None)
            impl.listener.onActivate(0, old_generation)
            impl.listener.onVisible(0, old_generation)
            impl.listener.onContext(0, old_generation)
            impl.interface.on_select.assert_not_called()
            impl.interface.row_visible.assert_not_called()
            impl.interface.on_primary_action.assert_not_called()
            impl.listener.onActivate(0, impl.generation)
            impl.listener.onVisible(0, impl.generation)
            impl.listener.onContext(0, impl.generation)
            impl.interface.on_select.assert_called_once()
            impl.interface.row_visible.assert_called_once_with(0)
            impl.interface.on_primary_action.assert_called_once_with(row=current)

    def test_palette_refresh_updates_group_outline_and_selection_together(self):
        modules = {
            'toga_android.widgets.base': NS(Widget=object),
            'java': NS(dynamic_proxy=lambda cls: object),
            'io.github.ispaure.commonutils': NS(FileListView=object),
            'android.graphics': NS(Color=NS(parseColor=lambda value: value)),
        }
        path = Path(__file__).parents[2] / 'ui/native/recycled_list_android.py'
        spec = importlib.util.spec_from_file_location('commonUtils.ui.native._android_list_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(module)
            impl = module.AndroidFileList()
            impl.native = Mock()
            config = impl.native.getResources.return_value.getConfiguration.return_value
            for high_contrast, mode, palette in ((False, 0x10, LIGHT), (True, 0x20, EINK),
                                                   (False, 0x20, DARK)):
                impl.interface = NS(appearance=NS(high_contrast=lambda: high_contrast,
                    palette=lambda dark: EINK if high_contrast else DARK if dark else LIGHT))
                config.uiMode = mode
                impl.refresh_palette()
                colors = impl.native.setPalette.call_args.args
                self.assertEqual(colors[-2:], (palette['border'], high_contrast))
                self.assertEqual(colors[3], '#ffffff' if high_contrast else palette['text'])
                self.assertEqual(colors[4], '#000000' if high_contrast else palette['hover'])
