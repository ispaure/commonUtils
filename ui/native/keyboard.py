"""Optional keyboard dismissal without application or editor ownership."""
import weakref

_apple_delegate = None


def native_value(value):
    return value() if callable(value) else value


class KeyboardDismissal:
    def __init__(self, native, gesture, delegate):
        self.native, self.gesture, self.delegate = native, gesture, delegate

    def dispose(self):
        if self.native is not None:
            self.native.removeGestureRecognizer(self.gesture)
            self.gesture.delegate = None
            self.native = self.gesture = self.delegate = None


def install(window):
    if not type(window._impl).__module__.startswith('toga_iOS.'):
        return
    global _apple_delegate
    from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, SEL
    if _apple_delegate is None:
        class NativeKeyboardDismissal(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
            @objc_method
            def outsideTap_(self, gesture) -> None:
                pass

            @objc_method
            def gestureRecognizer_shouldReceiveTouch_(self, gesture, touch) -> bool:
                touched = view = native_value(touch.view)
                # Text controls must keep selection, cursor and keyboard behavior.
                while view is not None:
                    if (view.isKindOfClass(ObjCClass('UITextField'))
                            or (view.isKindOfClass(ObjCClass('UITextView')) and native_value(view.editable))
                            or view.isKindOfClass(ObjCClass('WKWebView'))):
                        return False
                    view = native_value(view.superview)
                window = native_value(touched.window) if touched is not None else None
                if window is not None:
                    window.endEditing(True)
                # Observe only: buttons, scrolling and other gestures still win.
                return False
        _apple_delegate = NativeKeyboardDismissal
    delegate = _apple_delegate.alloc().init()
    gesture = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget(
        delegate, action=SEL('outsideTap:'))
    gesture.delegate = delegate
    gesture.cancelsTouchesInView = False
    window._impl.native.addGestureRecognizer(gesture)

    return KeyboardDismissal(window._impl.native, gesture, delegate)


class SearchDismissal:
    """One Android outside-touch listener, bound to explicit widget subtrees."""
    def __init__(self, search):
        self.search = getattr(search._impl, 'native', None)
        self.listener = None
        if not type(search._impl).__module__.startswith('toga_android.'):
            return
        from android.content import Context
        from android.view import View, MotionEvent
        from java import dynamic_proxy
        owner = weakref.ref(self)
        class OutsideTouch(dynamic_proxy(View.OnTouchListener)):
            def onTouch(self, view, event):
                current = owner()
                search = current.search if current is not None else None
                if search is not None and event.getAction() == MotionEvent.ACTION_DOWN and search.hasFocus():
                    search.clearFocus()
                    manager = view.getContext().getSystemService(Context.INPUT_METHOD_SERVICE)
                    manager.hideSoftInputFromWindow(search.getWindowToken(), 0)
                return False
        self.listener = OutsideTouch()

    def bind(self, roots):
        if self.listener is None or self.search is None:
            return
        from android.view import ViewGroup
        from android.widget import EditText
        listener = self.listener
        def bind(view):
            if isinstance(view, EditText):
                return
            view.setOnTouchListener(listener)
            if isinstance(view, ViewGroup):
                for index in range(view.getChildCount()):
                    bind(view.getChildAt(index))
        def mark(widget):
            widget._impl._search_keyboard_touch = listener
            for child in widget.children:
                mark(child)
        def bind_widget(widget):
            if getattr(widget._impl, '_search_keyboard_touch', None) is not listener:
                bind(widget._impl.native)
                mark(widget)
            else:
                for child in widget.children:
                    bind_widget(child)
        for root in roots:
            bind_widget(root)

    def dispose(self):
        # Installed native listeners become no-ops without retaining row widgets.
        self.search = None
