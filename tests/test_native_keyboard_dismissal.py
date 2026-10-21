"""Keyboard gestures preserve text controls and never consume outside taps."""
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from commonUtils.ui.native import keyboard


class AppleKeyboardTests(unittest.TestCase):
    def delegate(self):
        class NativeObject:
            def __init_subclass__(cls, protocols=()):
                pass

            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

        gesture = NS()
        def objc_class(name):
            if name == 'NSObject':
                return NativeObject
            if name == 'UITapGestureRecognizer':
                return NS(alloc=lambda: NS(initWithTarget=lambda *args, **kwargs: gesture))
            return name

        native = NS(addGestureRecognizer=Mock(), removeGestureRecognizer=Mock())
        implementation = type('Window', (), {'__module__': 'toga_iOS.window'})()
        implementation.native = native
        app = NS(main_window=NS(_impl=implementation))
        objc = NS(ObjCClass=objc_class, ObjCProtocol=lambda name: name,
                  objc_method=lambda method: method, SEL=lambda name: name)
        with patch.object(keyboard, '_apple_delegate', None), patch.dict(sys.modules, {'rubicon.objc': objc}):
            binding = keyboard.install(app.main_window)
        self.assertFalse(gesture.cancelsTouchesInView)
        self.addCleanup(binding.dispose)
        return binding.delegate

    def view(self, kind, parent=None, *, editable=True, getters=False, window=None):
        value = lambda item: (lambda: item) if getters else item
        return NS(isKindOfClass=lambda name: name == kind,
                  superview=value(parent), editable=value(editable), window=value(window))

    def test_outside_tap_handles_properties_and_getters_without_consuming_touch(self):
        delegate = self.delegate()
        for getters in (False, True):
            with self.subTest(getters=getters):
                window = NS(endEditing=Mock())
                parent = self.view('UIView', getters=getters)
                leaf = self.view('UIButton', parent, getters=getters, window=window)
                touch = NS(view=(lambda: leaf) if getters else leaf)
                self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, touch))
                window.endEditing.assert_called_once_with(True)

    def test_text_controls_and_web_content_keep_keyboard_and_selection(self):
        delegate = self.delegate()
        for kind, editable in (('UITextField', True), ('UITextView', True), ('WKWebView', False)):
            for getters in (False, True):
                with self.subTest(kind=kind, getters=getters):
                    window = NS(endEditing=Mock())
                    parent = self.view(kind, editable=editable, getters=getters)
                    leaf = self.view('UIView', parent, getters=getters, window=window)
                    self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, NS(view=leaf)))
                    window.endEditing.assert_not_called()

    def test_detached_or_missing_touch_view_is_safe(self):
        delegate = self.delegate()
        for leaf in (None, self.view('UIView')):
            self.assertFalse(delegate.gestureRecognizer_shouldReceiveTouch_(None, NS(view=leaf)))


class AndroidBrowserBindingTests(unittest.TestCase):
    def test_retained_controls_keep_one_listener_and_new_rows_dismiss_without_consuming_touch(self):
        class View:
            OnTouchListener = object
            def __init__(self):
                self.setOnTouchListener = Mock()
        class ViewGroup(View):
            def __init__(self, children=()):
                super().__init__()
                self.children = list(children)
            def getChildCount(self):
                return len(self.children)
            def getChildAt(self, index):
                return self.children[index]
        class EditText(View):
            pass
        class Impl:
            __module__ = 'toga_android.widgets.box'
            def __init__(self, native):
                self.native = native
        def widget(native, children=()):
            return NS(_impl=Impl(native), children=list(children))

        search_native = EditText()
        search_native.hasFocus = Mock(return_value=True)
        search_native.clearFocus = Mock()
        search_native.getWindowToken = Mock(return_value='token')
        search = widget(search_native)
        button_native = View()
        button = widget(button_native)
        root_native = ViewGroup([search_native, button_native])
        root = widget(root_native, [search, button])
        modules = {
            'android.content': NS(Context=NS(INPUT_METHOD_SERVICE='ime')),
            'android.view': NS(View=View, ViewGroup=ViewGroup, MotionEvent=NS(ACTION_DOWN=0)),
            'android.widget': NS(EditText=EditText),
            'java': NS(dynamic_proxy=lambda interface: object),
        }
        with patch.dict(sys.modules, modules):
            binding = keyboard.SearchDismissal(search)
            binding.bind([root])
            listener = binding.listener
            binding.bind([root])
            self.assertIs(binding.listener, listener)
            root_native.setOnTouchListener.assert_called_once_with(listener)
            button_native.setOnTouchListener.assert_called_once_with(listener)
            search_native.setOnTouchListener.assert_not_called()

            internal_label = View()
            new_native = ViewGroup([internal_label])
            new = widget(new_native)
            root.children.append(new)
            root_native.children.append(new_native)
            binding.bind([new])
            binding.bind([root])
            new_native.setOnTouchListener.assert_called_once_with(listener)
            internal_label.setOnTouchListener.assert_called_once_with(listener)
            button_native.setOnTouchListener.assert_called_once_with(listener)
            manager = NS(hideSoftInputFromWindow=Mock())
            new_native.getContext = lambda: NS(getSystemService=lambda kind: manager)
            self.assertFalse(listener.onTouch(new_native, NS(getAction=lambda: 0)))
            search_native.clearFocus.assert_called_once()
            manager.hideSoftInputFromWindow.assert_called_once_with('token', 0)

            binding.dispose()
            search_native.clearFocus.reset_mock()
            self.assertFalse(listener.onTouch(new_native, NS(getAction=lambda: 0)))
            search_native.clearFocus.assert_not_called()
