"""Toga ImageView extension with native bounded pinch/pan and fit-page paging."""
import toga

_scroll_class = None


def apple_scroll_class():
    global _scroll_class
    if _scroll_class is None:
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property
        from rubicon.objc.runtime import send_super
        from rubicon.objc import objc_id
        from ctypes import c_bool
        class CommonUtilsImageScroll(ObjCClass('UIScrollView'), protocols=(ObjCProtocol('UIScrollViewDelegate'), ObjCProtocol('UIGestureRecognizerDelegate'))):
            owner = objc_property(object, weak=True)

            @objc_method
            def layoutSubviews(self) -> None:
                send_super(CommonUtilsImageScroll, self, 'layoutSubviews')
                if self.owner is not None:
                    self.owner.layout_image()

            @objc_method
            def viewForZoomingInScrollView_(self, scroll):
                return self.owner.picture if self.owner is not None else None

            @objc_method
            def scrollViewDidZoom_(self, scroll) -> None:
                if self.owner is not None:
                    self.owner.center_image()

            @objc_method
            def scrollViewWillBeginZooming_withView_(self, scroll, view) -> None:
                if self.owner is not None:
                    self.owner.hold.enabled = False
                    self.owner.hide_magnifier()

            @objc_method
            def scrollViewDidEndZooming_withView_atScale_(self, scroll, view, scale: float) -> None:
                if self.owner is not None:
                    self.owner.hold.enabled = self.owner.interface.magnifier_enabled

            @objc_method
            def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                if self.owner is None:
                    return False
                # A second finger must still be able to start pinch zoom after
                # the hold has won; the zoom delegate cancels the lens.
                return ((gesture == self.owner.hold and other == self.pinchGestureRecognizer)
                        or (other == self.owner.hold and gesture == self.pinchGestureRecognizer))

            @objc_method
            def gestureRecognizerShouldBegin_(self, gesture) -> bool:
                if self.owner is not None and gesture in self.owner.swipes:
                    return self.zoomScale <= 1.05
                return bool(send_super(CommonUtilsImageScroll, self, 'gestureRecognizerShouldBegin:', gesture,
                                       restype=c_bool, argtypes=[objc_id]))

            @objc_method
            def gestureRecognizer_shouldReceiveTouch_(self, gesture, touch) -> bool:
                if self.owner is None:
                    return False
                if gesture not in self.owner.swipes and gesture != self.owner.tap:
                    return True
                if gesture in self.owner.swipes and self.owner.interface.page_swipes_at_edges:
                    return True
                x = touch.locationInView(self).x
                return 24 < x < self.bounds.size.width - 24

            @objc_method
            def magnify_(self, gesture) -> None:
                if self.owner is not None:
                    if gesture.state in (1, 2):  # began / changed
                        self.owner.show_magnifier(gesture)
                    else:
                        self.owner.hide_magnifier()

            @objc_method
            def didMoveToWindow(self) -> None:
                send_super(CommonUtilsImageScroll, self, 'didMoveToWindow')
                window = self.window
                if callable(window):
                    window = window()
                if self.owner is not None and window is None:
                    self.owner.hide_magnifier()

            @objc_method
            def toggleControls_(self, gesture) -> None:
                if self.owner is not None:
                    self.owner.interface.toggle_controls()

            @objc_method
            def pageSwipe_(self, gesture) -> None:
                if self.owner is not None and self.zoomScale <= 1.05:
                    self.owner.interface.page(-1 if gesture.direction == 1 else 1)
        _scroll_class = CommonUtilsImageScroll
    return _scroll_class


def apple_backend(interface):
    from toga_iOS.widgets.imageview import ImageView
    from rubicon.objc import ObjCClass, CGRect, CGSize, CGPoint, UIEdgeInsets, SEL
    class Backend(ImageView):
        def create(self):
            self.picture = ObjCClass('UIImageView').alloc().init()
            self.picture.contentMode = 1
            self.last_size = None
            self.lens = self.lens_picture = None
            self.native = apple_scroll_class().alloc().init()
            self.native.owner = self
            self.native.delegate = self.native
            self.native.minimumZoomScale, self.native.maximumZoomScale = 1, 6
            self.native.bounces = False
            # Navigation owns safe-area layout. UIKit's automatic scroll insets
            # otherwise retain bar offsets when this reader is reattached.
            self.native.contentInsetAdjustmentBehavior = 2  # never
            self.native.accessibilityLabel = self.interface.description
            self.native.isAccessibilityElement = True
            self.native.clipsToBounds = True
            self.native.addSubview(self.picture)
            self.native.setTranslatesAutoresizingMaskIntoConstraints(False)
            self.native.setAutoresizesSubviews(False)
            self.swipes = []
            for direction in (1, 2):
                gesture = ObjCClass('UISwipeGestureRecognizer').alloc().initWithTarget(self.native, action=SEL('pageSwipe:'))
                gesture.direction, gesture.delegate = direction, self.native
                self.native.addGestureRecognizer(gesture)
                self.native.panGestureRecognizer.requireGestureRecognizerToFail(gesture)
                self.swipes.append(gesture)
            self.tap = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget(self.native, action=SEL('toggleControls:'))
            self.tap.delegate = self.native
            self.native.addGestureRecognizer(self.tap)
            for gesture in self.swipes:
                self.tap.requireGestureRecognizerToFail(gesture)
            self.hold = ObjCClass('UILongPressGestureRecognizer').alloc().initWithTarget(self.native, action=SEL('magnify:'))
            self.hold.delegate = self.native
            self.hold.minimumPressDuration = .4
            self.hold.allowableMovement = 10
            self.hold.numberOfTouchesRequired = 1
            self.hold.enabled = self.interface.magnifier_enabled
            self.native.addGestureRecognizer(self.hold)
            self.tap.requireGestureRecognizerToFail(self.hold)
            self.native.panGestureRecognizer.requireGestureRecognizerToFail(self.hold)
            self.add_constraints()

        def set_magnifier_enabled(self, enabled):
            self.hold.enabled = enabled
            if not enabled:
                self.hide_magnifier()

        def hide_magnifier(self):
            if self.lens is not None:
                self.lens_picture.image = None
                self.lens.removeFromSuperview()
                self.lens = self.lens_picture = None

        def show_magnifier(self, gesture):
            parent = self.native.superview
            if callable(parent):
                parent = parent()
            if parent is None or self.picture.image is None or not self.interface.magnifier_enabled:
                self.hide_magnifier()
                return
            source = gesture.locationInView(self.picture)
            size = self.picture.bounds.size
            if self.lens is None:
                # Ignore holds in the letterbox, but allow an active lens to
                # follow the thumb across page edges without changing gestures.
                if not (0 <= source.x <= size.width and 0 <= source.y <= size.height):
                    return
                self.lens = ObjCClass('UIView').alloc().init()
                self.lens.userInteractionEnabled = False
                self.lens.clipsToBounds = True
                self.lens.layer.cornerRadius = 24
                self.lens.layer.borderWidth = 2
                self.lens.layer.borderColor = ObjCClass('UIColor').whiteColor.CGColor
                self.lens.backgroundColor = ObjCClass('UIColor').blackColor
                self.lens_picture = ObjCClass('UIImageView').alloc().init()
                self.lens_picture.image = self.picture.image
                self.lens.addSubview(self.lens_picture)
                parent.addSubview(self.lens)
            # Convert through the native hierarchy: scroll offsets, fit margins
            # and zoom are all included, and the lens itself never scrolls.
            thumb = gesture.locationInView(parent)
            rect = self.native.convertRect(self.native.bounds, toView=parent)
            width, height = min(180, rect.size.width), min(140, rect.size.height)
            x = max(rect.origin.x, min(thumb.x - width / 2, rect.origin.x + rect.size.width - width))
            y = thumb.y - height - 36
            if y < rect.origin.y:
                y = thumb.y + 36
            y = max(rect.origin.y, min(y, rect.origin.y + rect.size.height - height))
            self.lens.frame = CGRect((x, y), (width, height))
            scale = 2.5 * float(self.native.zoomScale)
            sx, sy = max(0, min(source.x, size.width)), max(0, min(source.y, size.height))
            self.lens_picture.frame = CGRect((width / 2 - sx * scale, height / 2 - sy * scale),
                                              (size.width * scale, size.height * scale))

        def set_image(self, image):
            self.hide_magnifier()
            self.native.setZoomScale(1, animated=False)
            self.picture.image = image._impl.native if image else None
            self.last_size = None
            self.layout_image()

        def layout_image(self):
            size = self.native.bounds.size
            key = (size.width, size.height)
            image = getattr(self.interface, 'image', None)
            if image is None or min(key) <= 0:
                return
            if key == self.last_size:
                self.center_image()
                return
            self.hide_magnifier()
            self.last_size = key
            zoom = float(self.native.zoomScale)
            self.native.setZoomScale(1, animated=False)
            scale = min(size.width / image.width, size.height / image.height)
            width, height = image.width * scale, image.height * scale
            self.picture.frame = CGRect((0, 0), (width, height))
            self.native.contentSize = CGSize(width, height)
            self.native.setZoomScale(zoom, animated=False)
            self.center_image()

        def center_image(self):
            bounds, content = self.native.bounds.size, self.native.contentSize
            top = max(0, (bounds.height - content.height) / 2)
            left = max(0, (bounds.width - content.width) / 2)
            self.native.contentInset = UIEdgeInsets(top, left, top, left)
            if float(self.native.zoomScale) <= 1.05:
                # Fit-page has one valid position. Restore it even when only
                # the navigation/safe-area state changed, not the bounds size.
                offset = self.native.contentOffset
                if abs(offset.x + left) > .01 or abs(offset.y + top) > .01:
                    self.native.setContentOffset(CGPoint(-left, -top), animated=False)
    return Backend(interface=interface)


def android_backend(interface):
    from toga_android.widgets.imageview import ImageView
    from java import jclass, dynamic_proxy
    View = jclass('io.github.ispaure.commonutils.ImageCanvasView')
    class Backend(ImageView):
        def create(self):
            self.native = View(self._native_activity)
            self.native.setContentDescription(self.interface.description)
            owner = self
            class Listener(dynamic_proxy(View.PageListener)):
                def page(self, direction):
                    owner.interface.page(direction)
                def toggleControls(self):
                    owner.interface.toggle_controls()
            self.listener = Listener()
            self.native.setPageListener(self.listener)
            self.native.setMagnifierEnabled(self.interface.magnifier_enabled)

        def set_magnifier_enabled(self, enabled):
            self.native.setMagnifierEnabled(enabled)

        def rehint(self):
            super().rehint()
            self.native.setScaleType(self.native.ScaleType.MATRIX)
    return Backend(interface=interface)


class ImageCanvas(toga.ImageView):
    def __init__(self, *args, on_page=None, on_toggle=None, page_swipes_at_edges=False, magnifier_enabled=False, description='Image. Pinch to zoom; swipe at fit size to change images.', **kwargs):
        self._magnifier_enabled = bool(magnifier_enabled)
        self.description = description
        self.page_swipes_at_edges = page_swipes_at_edges
        self.on_page = on_page
        self.on_toggle = on_toggle
        super().__init__(*args, **kwargs)

    def _create(self):
        backend = self.factory.ImageView.__module__
        if backend.startswith('toga_iOS.'):
            return apple_backend(self)
        if backend.startswith('toga_android.'):
            return android_backend(self)
        return super()._create()

    @property
    def magnifier_enabled(self):
        return self._magnifier_enabled

    @magnifier_enabled.setter
    def magnifier_enabled(self, enabled):
        self._magnifier_enabled = bool(enabled)
        setter = getattr(self._impl, 'set_magnifier_enabled', None)
        if setter is not None:
            setter(self._magnifier_enabled)

    def page(self, direction):
        if self.on_page is not None and self.image is not None and self.zoom_scale <= 1.05:
            self.on_page(direction)

    def toggle_controls(self):
        if self.on_toggle is not None:
            self.on_toggle()

    @property
    def zoom_scale(self):
        backend = type(self._impl).__module__
        native = getattr(self._impl, 'native', None)
        if native is None:
            return 1
        if hasattr(self._impl, 'picture'):
            return float(native.zoomScale)
        if backend == __name__:
            return float(native.getZoom())
        return 1

    def set_zoom(self, value):
        value = max(1, min(6, float(value)))
        native = getattr(self._impl, 'native', None)
        if hasattr(self._impl, 'picture'):
            native.setZoomScale(value, animated=False)
        elif native is not None and type(self._impl).__module__ == __name__:
            native.setZoom(value)

    def fit_page(self, widget=None, **kwargs):
        self.set_zoom(1)

    def dispose(self):
        """Retire callbacks and native gesture ownership before dropping a page."""
        self.magnifier_enabled = False
        self.on_page = self.on_toggle = None
        self.image = None
        if hasattr(self._impl, 'picture'):
            self._impl.native.delegate = None
            # Rubicon's weak property setter cannot accept None. The owner is
            # already weak; disable events rather than assigning a nil owner.
            self._impl.native.userInteractionEnabled = False
        elif hasattr(self._impl, 'listener'):
            self._impl.native.setPageListener(None)
            self._impl.listener = None
