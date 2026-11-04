"""Tree callbacks retain the recycled list's source and enabled-state boundary."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


class RecycledTreeRowsTests(unittest.TestCase):
    def setUp(self):
        modules = {'toga_android.widgets.base': NS(Widget=object),
                   'java': NS(dynamic_proxy=lambda protocol: object),
                   'io.github.ispaure.commonutils': NS(FileListView=NS())}
        with patch.dict('sys.modules', modules):
            spec = importlib.util.spec_from_file_location('_tree_adapter',
                Path(__file__).parents[2] / 'ui/native/recycled_list_android.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.impl = module.AndroidFileList()
        self.actions = NS(end_drag=Mock(), drag_token='opaque-token')
        self.rows = [NS(title='Folder', subtitle='', folder=True, tree_depth=0,
                        tree_expanded=True, tree_landing=True),
                     NS(title='Note.md', subtitle='', folder=False, tree_depth=1,
                        tree_expanded=None, tree_landing=False)]
        self.impl.interface = NS(enabled=True, updating=False, data=self.rows, tree_actions=self.actions,
            tree_landing_icon=NS(_impl=NS(native='landing-bitmap')),
            appearance=NS(icon=lambda folder: None))
        self.impl.generation = 3
        self.impl.native = Mock()

    def test_only_current_enabled_source_can_supply_tree_actions(self):
        self.assertEqual(self.impl.tree_row(1, 3), (self.actions, self.rows[1]))
        for index, generation in ((-1, 3), (2, 3), (1, 2)):
            self.assertIsNone(self.impl.tree_row(index, generation))
        self.impl.interface.enabled = False
        self.assertIsNone(self.impl.tree_row(1, 3))
        self.impl.interface.enabled = True
        self.impl.interface.updating = True
        self.assertIsNone(self.impl.tree_row(1, 3))

    def test_source_replacement_ends_drag_and_publishes_tree_metadata_in_bulk(self):
        self.impl.change_source(self.rows)
        self.actions.end_drag.assert_called_once_with()
        self.impl.native.setTreeRows.assert_called_once_with(
            [0, 1], [1, -1], [True, False], 'landing-bitmap', 'opaque-token')
        self.assertEqual(self.impl.generation, 4)
        self.assertIsNone(self.impl.tree_row(1, 3))
        self.impl.native.setRows.assert_called_once_with(
            ['Folder', 'Note.md'], ['', ''], [True, False], 4)

    def test_ordinary_lists_do_not_enable_tree_rows_or_drag(self):
        self.impl.interface.tree_actions = None
        self.impl.change_source(self.rows)
        self.impl.native.setTreeRows.assert_not_called()
        self.actions.end_drag.assert_not_called()
        self.assertIsNone(self.impl.tree_row(0, 4))
