"""Contextual row buttons never activate a file or act on replaced sources."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


class Button:
    @classmethod
    def alloc(cls):
        return cls()

    def initWithFrame(self, frame):
        self.titleLabel = NS()
        self.setTitle = Mock()
        self.setTitleColor = Mock()
        self.addTarget = Mock()
        return self


class Interface:
    pass


class FileRowActionTests(unittest.TestCase):
    def setUp(self):
        modules = {
            'rubicon.objc': NS(objc_method=lambda method: method, ObjCInstance=object,
                ObjCBlock=Mock(), Block=Mock(), objc_id=object, ns_from_py=lambda value: value,
                objc_property=lambda *args, **kw: None,
                ObjCClass=lambda name: Button if name == 'UIButton' else NS(systemFontOfSize=lambda size: size),
                SEL=lambda value: value, CGRect=lambda *args: args),
            'toga_iOS.widgets.detailedlist': NS(DetailedList=object, TogaTableViewController=object),
            'toga_iOS.libs': NS(UITableViewCell=Mock(), UITableViewCellStyleSubtitle=1, UIView=Mock()),
        }
        self.enterContext(patch.dict('sys.modules', modules))
        path = Path(__file__).parents[2] / 'ui/native/recycled_list_ios.py'
        spec = importlib.util.spec_from_file_location('commonUtils.ui.native._row_action_test', path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.row = NS(index=0, title='Example.md')
        self.interface = Interface()
        self.interface.__dict__.update(_primary_action='Select', _impl=NS(primary_action_enabled=True),
                                      data=[self.row], enabled=True, on_primary_action=Mock(),
                                      appearance=NS(apple_color=lambda role: role, row_height=48))
        self.cell = NS(accessoryView=None)
        self.module._bind_actions(self.interface, self.cell, self.row)

    def test_visible_button_selects_current_row_and_has_filename_label(self):
        button = self.cell.accessoryView
        self.assertEqual(button.accessibilityLabel, 'Select Example.md')
        button.selectRow_(button)
        self.interface.on_primary_action.assert_called_once_with(row=self.row)

    def test_source_replacement_and_disabled_table_reject_old_row_actions(self):
        button = self.cell.accessoryView
        self.interface.data = [NS(index=0, title='Replacement.md')]
        button.selectRow_(button)
        self.interface.data = [self.row]
        self.interface.enabled = False
        button.selectRow_(button)
        self.interface.on_primary_action.assert_not_called()

    def test_retired_private_cell_clears_button_reference_and_accessibility_name(self):
        button = self.cell.accessoryView
        self.module._clear_actions(self.cell)
        self.assertIsNone(button.row)
        self.assertEqual(button.accessibilityLabel, '')
        button.selectRow_(button)
        self.interface.on_primary_action.assert_not_called()

    def test_lists_without_contextual_handler_have_no_ellipsis(self):
        self.interface._impl.primary_action_enabled = False
        self.module._bind_actions(self.interface, self.cell, self.row)
        self.assertIsNone(self.cell.accessoryView)

    def test_async_menu_retains_copied_completion_until_delivery(self):
        import asyncio
        import gc
        import weakref
        import sys

        class Completion:
            pass

        async def exercise():
            copied, delivered, tasks = [], [], []
            ready = asyncio.Event()

            def copy():
                owner = Completion()
                copied.append(weakref.ref(owner))
                return owner

            def block(owner, *signature):
                # Rubicon's ObjCBlock retains a pointer, not its Python owner.
                reference = weakref.ref(owner)
                def complete(children):
                    self.assertIsNotNone(reference(), 'Native completion was released before delivery')
                    delivered.append(children)
                return complete

            async def commands(row):
                await ready.wait()
                return ['Open', 'Rename']

            def spawn(coroutine):
                tasks.append(asyncio.create_task(coroutine))

            bridge = sys.modules['rubicon.objc']
            with patch.object(bridge, 'Block', side_effect=lambda callback, *args: callback), \
                    patch.object(bridge, 'ObjCClass', return_value=Mock()), \
                    patch.object(self.module, 'ObjCInstance', return_value=NS(copy=copy)), \
                    patch.object(self.module, 'ObjCBlock', side_effect=block), \
                    patch.dict(sys.modules, {'toga': NS(App=NS(app=NS(loop=NS(create_task=spawn))))}):
                self.interface.menu_provider = commands
                self.module._bind_actions(self.interface, self.cell, self.row)
                self.cell.accessoryView.menu_provider_block('native completion pointer')
                gc.collect()
                self.assertIsNotNone(copied[0]())
                await asyncio.sleep(0)
                ready.set()
                await asyncio.gather(*tasks)
                self.assertEqual(delivered, [['Open', 'Rename']])

        asyncio.run(exercise())
