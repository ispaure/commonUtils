"""UIKit tree callbacks reject replaced sources and foreign drag sessions."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import weakref

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class Native:
    def __init_subclass__(cls, **kwargs):
        pass


class Interface:
    pass


class IOSTreeTests(unittest.TestCase):
    def setUp(self):
        self.classes = {name: Mock() for name in ('NSItemProvider', 'UIDragItem', 'UIDropProposal')}
        bridge = NS(ObjCClass=lambda name: self.classes.get(name, Native), ObjCProtocol=lambda name: object,
                    objc_method=lambda method: method, objc_property=lambda kind: None,
                    ns_from_py=lambda value: value, SEL=lambda value: value, CGRect=lambda *args: args)
        with patch.dict('sys.modules', {'rubicon.objc': bridge, 'rubicon.objc.types': NS(NSInteger=int)}):
            spec = importlib.util.spec_from_file_location('_ios_tree_test',
                Path(__file__).parents[2] / 'ui/native/recycled_tree_ios.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.interface = Interface()
        self.row = NS(index=0, folder=True, tree_depth=2, tree_expanded=False)
        self.actions = NS(current=Mock(return_value=True), toggle=Mock(), start_drag=Mock(return_value=True),
                          can_drop=Mock(return_value=True), drop=Mock(), end_drag=Mock(), drag_token='opaque-token')
        self.interface.data = [self.row]
        self.interface.enabled, self.interface.updating = True, False
        self.interface.tree_actions = self.actions
        self.interface.appearance = NS(apple_color=lambda name: name, icon_size=20)
        self.owner = weakref.ref(self.interface)

    def test_disclosure_rejects_disabled_updating_replaced_and_inactive_rows(self):
        button = self.module.TreeDisclosure()
        button.owner, button.row = self.owner, self.row
        button.toggle_(button)
        self.actions.toggle.assert_called_once_with(self.row)
        for change, restore in ((lambda: setattr(self.interface, 'enabled', False),
                                 lambda: setattr(self.interface, 'enabled', True)),
                                (lambda: setattr(self.interface, 'updating', True),
                                 lambda: setattr(self.interface, 'updating', False)),
                                (lambda: setattr(self.interface, 'data', [object()]),
                                 lambda: setattr(self.interface, 'data', [self.row])),
                                (lambda: setattr(self.actions.current, 'return_value', False),
                                 lambda: setattr(self.actions.current, 'return_value', True))):
            change()
            button.toggle_(button)
            self.actions.toggle.assert_called_once()
            restore()

    def test_drag_payload_is_opaque_and_restricted_to_the_application(self):
        delegate = self.module.TreeDrag()
        delegate.owner, delegate.row = self.owner, self.row
        session = NS()
        items = delegate.dragInteraction_itemsForBeginningSession_(None, session)
        self.actions.start_drag.assert_called_once_with(self.row)
        self.classes['NSItemProvider'].alloc().initWithObject.assert_called_once_with('opaque-token')
        self.assertEqual(session.localContext, 'opaque-token')
        self.assertEqual(len(items), 1)
        self.assertTrue(delegate.dragInteraction_sessionIsRestrictedToDraggingApplication_(None, session))
        self.actions.start_drag.return_value = False
        self.assertEqual(delegate.dragInteraction_itemsForBeginningSession_(None, session), [])

    def test_drop_rechecks_identity_local_session_token_and_controller_authorization(self):
        delegate = self.module.TreeDrop()
        delegate.owner, delegate.row, delegate.cell = self.owner, self.row, NS()
        session = NS(localDragSession=NS(localContext='opaque-token'))
        self.assertTrue(delegate.dropInteraction_canHandleSession_(None, session))
        delegate.dropInteraction_sessionDidUpdate_(None, session)
        self.classes['UIDropProposal'].alloc().initWithDropOperation.assert_called_with(3)
        self.assertEqual(delegate.cell.backgroundColor, 'hover')
        delegate.dropInteraction_performDrop_(None, session)
        self.actions.drop.assert_called_once_with(self.row)
        for invalid in (NS(localDragSession=None), NS(localDragSession=NS(localContext='other-library'))):
            self.assertFalse(delegate.dropInteraction_canHandleSession_(None, invalid))
            delegate.dropInteraction_performDrop_(None, invalid)
            self.actions.drop.assert_called_once()
        self.interface.data = [object()]
        self.assertFalse(delegate.dropInteraction_canHandleSession_(None, session))

    def test_retirement_removes_private_row_references_and_late_disclosure_callbacks(self):
        button = self.module.TreeDisclosure()
        button.owner, button.row, button.setHidden = self.owner, self.row, Mock()
        drag, drop = self.module.TreeDrag(), self.module.TreeDrop()
        drag.owner = drop.owner = self.owner
        drag.row = drop.row = self.row
        cell = NS(tree_owner=self.owner, tree_row=self.row, tree_disclosure=button,
                  tree_drag=(None, drag), tree_drop=(None, drop), textLabel=NS(attributedText='Private'))
        drop.cell = cell
        self.module.clear(cell)
        self.assertIsNone(cell.tree_row)
        self.assertIsNone(cell.textLabel.attributedText)
        self.assertIsNone(drop.cell)
        button.toggle_(button)
        self.actions.toggle.assert_not_called()

    def test_layout_reserves_disclosure_and_action_width_without_overlapping_names(self):
        def rect(x, y, width, height):
            return NS(origin=NS(x=x, y=y), size=NS(width=width, height=height))
        cell = NS(tree_owner=self.owner, tree_row=self.row, bounds=rect(0, 0, 320, 48),
                  imageView=NS(), tree_disclosure=NS(), contentView=NS(bounds=rect(0, 0, 264, 48)),
                  textLabel=NS(frame=rect(0, 0, 200, 48)), detailTextLabel=NS(frame=rect(0, 28, 200, 16)))
        self.module.layout(cell)
        self.assertEqual(cell.tree_disclosure.frame, ((60, 0), (44, 48.0)))
        self.assertEqual(cell.textLabel.frame, ((104, 0), (156.0, 48)))
