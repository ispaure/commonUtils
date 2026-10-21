"""Native pinch text sizing and in-place WebView reflow with explicit callbacks."""
import inspect
import logging
import math
import re
import weakref

_apple_target = None


def native_backend(widget):
    # CodeInput and private WebViews supply subclasses outside Toga's namespace.
    return getattr(widget, 'backend_name', None) or next(
        (base.__module__ for base in type(widget._impl).__mro__
         if base.__module__.startswith(('toga_iOS.', 'toga_android.'))),
        type(widget._impl).__module__)



class TextSizeBinding:
    def __init__(self, widget, *, loop, get_size, save_size=None, changed=None,
                 active=lambda: True, alive=lambda: True, alignment=lambda: 'start',
                 alignment_variable='--text-align', minimum=12, maximum=32,
                 web=False, formatted=None, on_error=None, previous_touch=None):
        if type(minimum) is not int or type(maximum) is not int or minimum <= 0 or maximum < minimum:
            raise ValueError('Text size limits must be positive ordered integers')
        if not re.fullmatch(r'--[a-zA-Z_][a-zA-Z0-9_-]*', alignment_variable):
            raise ValueError('Expected a CSS custom property name')
        self.widget = weakref.ref(widget)
        self.loop, self.get_size, self.save_size, self.changed = loop, get_size, save_size, changed
        self.active, self.alive, self.alignment = active, alive, alignment
        self.alignment_variable, self.minimum, self.maximum = alignment_variable, minimum, maximum
        self.web, self.on_error, self.previous_touch = web, on_error, previous_touch
        self.formatted = weakref.ref(formatted) if formatted else lambda: None
        self.start = self.size = self.task = None
        self.closed = self._installed = False

    def gesture(self, state, scale=1):
        if self.closed or self.widget() is None or not self.active() or not self.alive():
            return
        if state == 'begin':
            self.disable_web_zoom()
            self.start = self.get_size()
            self.size = self.start
        elif self.start is not None and state == 'change' and math.isfinite(scale) and scale > 0:
            self.size = min(self.maximum, max(self.minimum, int(self.start * scale + .5)))
            self.apply(self.size)
        elif self.start is not None and state in {'end', 'cancel'}:
            size, self.start = self.size, None
            if state == 'end' and size != self.get_size() and self.save_size is not None:
                try:
                    self.save_size(size)
                except (OSError, ValueError) as error:
                    if self.on_error is not None:
                        self.on_error(error)
                    else:
                        logging.getLogger(__name__).warning('Could not save text size: %s', error)
            if self.changed is not None:
                self.changed()
            else:
                self.apply(self.get_size())

    def apply(self, size):
        widget = self.widget()
        if self.closed or widget is None or not self.alive():
            return
        if type(size) is not int or not self.minimum <= size <= self.maximum:
            raise ValueError('Text size is outside the configured limits')
        formatted = self.formatted()
        if formatted is not None:
            if formatted.closed:
                return
            formatted.font_size = size
        self.size = size
        if not self.web:
            widget.style.font_size = size
        elif self.task is None or self.task.done():
            self.task = self.loop.create_task(self.apply_web())

    async def apply_web(self):
        applied = None
        try:
            while True:
                widget = self.widget()
                if self.closed or widget is None or not self.alive():
                    return
                formatted = self.formatted()
                if formatted is not None and formatted.closed:
                    return
                alignment = self.alignment()
                if alignment not in {'start', 'left', 'right', 'center', 'justify'}:
                    raise ValueError('Unsupported text alignment')
                current = (self.size, alignment)
                if applied == current:
                    return
                applied = current
                await widget.evaluate_javascript(
                    "(()=>{const viewport=document.querySelector('meta[name=viewport]');"
                    "if(viewport)viewport.content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no';"
                    f"document.body.style.fontSize='{applied[0]}px';"
                    f"document.documentElement.style.setProperty('{self.alignment_variable}','{alignment}');"
                    "window.dispatchEvent(new Event('resize'));})()")
        except Exception:
            logging.getLogger(__name__).debug('Text surface retired during font update', exc_info=True)

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        if self.task is not None:
            self.task.cancel()
        widget = self.widget()
        if widget is not None:
            if hasattr(self, 'recognizer'):
                widget._impl.native.removeGestureRecognizer(self.recognizer)
                self.recognizer.delegate = None
            if hasattr(self, 'listener') and getattr(widget._impl, '_text_size_touch', None) is self.listener:
                widget._impl.native.setOnTouchListener(self.previous_touch)
                widget._impl._text_size_touch = None
            if self.web and getattr(self, '_load_handler', None) is widget.on_webview_load:
                widget.on_webview_load = self._previous_load_handler
        self.start = None

    def disable_web_zoom(self):
        widget = self.widget()
        if self.web and widget is not None and native_backend(widget).startswith('toga_iOS.'):
            # WebKit creates its scroll pinch recognizer lazily after loading.
            pinch = widget._impl.native.scrollView.pinchGestureRecognizer
            if pinch is not None:
                if hasattr(self, 'recognizer') and getattr(self, '_web_pinch', None) != pinch:
                    # WebKit may re-enable zoom during layout. Its recognizer
                    # must wait for our text-size gesture to fail as well.
                    pinch.requireGestureRecognizerToFail(self.recognizer)
                    self._web_pinch = pinch
                pinch.enabled = False

    def attach_load(self):
        widget = self.widget()
        if self.closed or not self.web or widget is None or getattr(self, '_load_handler', None) is widget.on_webview_load:
            return
        previous = widget.on_webview_load
        self._previous_load_handler = previous
        binding = weakref.ref(self)
        async def loaded(widget, **kwargs):
            result = previous(**kwargs) if previous is not None else None
            if inspect.isawaitable(result):
                await result
            current = binding()
            if current is not None and not current.closed and current.alive():
                current.disable_web_zoom()
                current.apply(current.get_size())
        widget.on_webview_load = loaded
        self._load_handler = widget.on_webview_load

    def install(self):
        widget = self.widget()
        if self.closed or self._installed or widget is None:
            return
        self._installed = True
        backend = native_backend(widget)
        if backend.startswith('toga_iOS.'):
            self.install_apple(widget._impl.native)
        elif backend.startswith('toga_android.'):
            self.install_android(widget._impl.native)

    def install_apple(self, native):
        global _apple_target
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property, SEL
        if _apple_target is None:
            class NativeTextPinch(ObjCClass('NSObject'), protocols=[ObjCProtocol('UIGestureRecognizerDelegate')]):
                binding = objc_property(object, weak=True)

                @objc_method
                def changed_(self, gesture) -> None:
                    states = {1: 'begin', 2: 'change', 3: 'end', 4: 'cancel', 5: 'cancel'}
                    if self.binding is not None and int(gesture.state) in states:
                        self.binding.gesture(states[int(gesture.state)], float(gesture.scale))

                @objc_method
                def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                    return not bool(other.isKindOfClass(ObjCClass('UIPinchGestureRecognizer')))
            _apple_target = NativeTextPinch
        self.target = _apple_target.new()
        self.target.binding = self
        self.recognizer = ObjCClass('UIPinchGestureRecognizer').alloc().initWithTarget(self.target, action=SEL('changed:'))
        self.recognizer.delegate = self.target
        self.recognizer.cancelsTouchesInView = True
        self.disable_web_zoom()
        native.addGestureRecognizer(self.recognizer)

    def install_android(self, native):
        from java import dynamic_proxy
        from android.view import View, MotionEvent
        reference = weakref.ref(self)
        previous = self.previous_touch
        class Touch(dynamic_proxy(View.OnTouchListener)):
            def __init__(self):
                super().__init__()
                self.distance = None
                self.scaling = False

            def onTouch(self, view, event):
                binding = reference()
                if binding is None or binding.closed:
                    return bool(previous.onTouch(view, event)) if previous is not None else False
                action = event.getActionMasked()
                if action == MotionEvent.ACTION_DOWN:
                    self.scaling, self.distance = False, None
                if event.getPointerCount() >= 2 and action != MotionEvent.ACTION_POINTER_UP:
                    distance = math.hypot(event.getX(0) - event.getX(1), event.getY(0) - event.getY(1))
                    if self.distance is None and distance > 0:
                        self.distance, self.scaling = distance, True
                        binding.gesture('begin')
                        # Cancel caret/scroll tracking before taking this gesture.
                        cancel = MotionEvent.obtain(event)
                        cancel.setAction(MotionEvent.ACTION_CANCEL)
                        view.onTouchEvent(cancel)
                        cancel.recycle()
                    if self.distance:
                        view.getParent().requestDisallowInterceptTouchEvent(True)
                        binding.gesture('change', distance / self.distance)
                if self.scaling:
                    if action in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL, MotionEvent.ACTION_POINTER_UP):
                        binding.gesture('cancel' if action == MotionEvent.ACTION_CANCEL else 'end')
                        self.distance = None
                    return True
                return bool(previous.onTouch(view, event)) if previous is not None else False
        self.listener = Touch()
        if self.web:
            native.getSettings().setSupportZoom(False)
        native.setOnTouchListener(self.listener)
        self.widget()._impl._text_size_touch = self.listener
