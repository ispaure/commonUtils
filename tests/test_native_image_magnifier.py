"""Lens image transforms and lifetime, without a UIKit runtime."""
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from commonUtils.ui.native.image_canvas import apple_backend


def rect(origin, size):
    return NS(origin=NS(x=origin[0], y=origin[1]), size=NS(width=size[0], height=size[1]))


class ImageView:
    def __init__(self, interface):
        self.interface = interface


class AppleLensTests(unittest.TestCase):
    def setUp(self):
        self.objects = []
        def objc_class(name):
            def allocate():
                native = Mock()
                native.init.return_value = native
                self.objects.append(native)
                return native
            return NS(alloc=allocate, whiteColor=NS(CGColor=object()), blackColor=object())
        self.modules = patch.dict(sys.modules, {
            'toga_iOS.widgets.imageview': NS(ImageView=ImageView),
            'rubicon.objc': NS(ObjCClass=objc_class, CGRect=rect, CGSize=Mock(),
                               CGPoint=Mock(), UIEdgeInsets=Mock(), SEL=lambda x: x),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.backend = apple_backend(NS(magnifier_enabled=True))
        self.backend.lens = self.backend.lens_picture = None
        self.backend.picture = NS(image=object(), bounds=rect((0, 0), (200, 300)))
        self.backend.native = Mock(zoomScale=2)
        self.backend.native.convertRect.return_value = rect((0, 0), (400, 800))
        self.backend.hold = NS(enabled=True)

    def gesture(self, image_x=40, image_y=60, thumb_x=100, thumb_y=400):
        return NS(locationInView=lambda target: NS(x=image_x, y=image_y)
                  if target is self.backend.picture else NS(x=thumb_x, y=thumb_y))

    def test_uses_original_pixels_and_image_coordinates_at_current_zoom(self):
        backend = self.backend
        backend.show_magnifier(self.gesture())
        self.assertIs(backend.lens_picture.image, backend.picture.image)
        frame = backend.lens_picture.frame
        self.assertEqual((frame.size.width, frame.size.height), (1000, 1500))
        self.assertEqual((frame.origin.x, frame.origin.y), (-110, -230))
        self.assertEqual(backend.lens.frame.origin.y, 224)
        # Moving keeps the same image and overlay, and clamps to the viewport.
        lens = backend.lens
        backend.show_magnifier(self.gesture(thumb_x=399, thumb_y=10))
        self.assertIs(backend.lens, lens)
        self.assertEqual((lens.frame.origin.x, lens.frame.origin.y), (220, 46))

    def test_ignores_initial_letterbox_hold_and_clears_pixels_when_disabled(self):
        backend = self.backend
        backend.show_magnifier(self.gesture(image_x=-10))
        self.assertIsNone(backend.lens)
        backend.show_magnifier(self.gesture())
        lens, picture = backend.lens, backend.lens_picture
        backend.set_magnifier_enabled(False)
        self.assertFalse(backend.hold.enabled)
        self.assertIsNone(picture.image)
        lens.removeFromSuperview.assert_called_once()
        self.assertIsNone(backend.lens)
        backend.hide_magnifier()  # cancellation/disposal can be repeated

    def test_detached_or_disabled_canvas_cannot_show_a_lens(self):
        backend = self.backend
        backend.interface.magnifier_enabled = False
        backend.show_magnifier(self.gesture())
        self.assertIsNone(backend.lens)
        backend.interface.magnifier_enabled = True
        backend.native.superview = None
        backend.show_magnifier(self.gesture())
        self.assertIsNone(backend.lens)


class AppleHoldLifecycleTests(unittest.TestCase):
    def test_release_cancel_pinch_and_detach_clear_the_lens(self):
        from commonUtils.ui.native import image_canvas
        class Scroll:
            def __init_subclass__(cls, protocols=()):
                pass
        objc = NS(ObjCClass=lambda name: Scroll, ObjCProtocol=lambda name: name,
                  objc_method=lambda method: method, objc_property=lambda *a, **kw: None,
                  objc_id=object)
        with patch.object(image_canvas, '_scroll_class', None), patch.dict(sys.modules, {
            'rubicon.objc': objc, 'rubicon.objc.runtime': NS(send_super=Mock()),
        }):
            native = image_canvas.apple_scroll_class()()
        owner = native.owner = Mock()
        owner.interface.magnifier_enabled = True
        for state in (1, 2):
            gesture = NS(state=state)
            native.magnify_(gesture)
            owner.show_magnifier.assert_called_with(gesture)
        for state in (3, 4, 5):  # ended, cancelled, failed
            owner.hide_magnifier.reset_mock()
            native.magnify_(NS(state=state))
            owner.hide_magnifier.assert_called_once()
        native.pinchGestureRecognizer = object()
        self.assertTrue(native.gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(
            owner.hold, native.pinchGestureRecognizer))
        native.scrollViewWillBeginZooming_withView_(native, None)
        self.assertFalse(owner.hold.enabled)
        native.scrollViewDidEndZooming_withView_atScale_(native, None, 2)
        self.assertTrue(owner.hold.enabled)
        owner.hide_magnifier.reset_mock()
        native.window = None
        native.didMoveToWindow()
        owner.hide_magnifier.assert_called_once()


if __name__ == '__main__':
    unittest.main()
