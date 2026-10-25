"""Lens image transforms and lifetime, without a UIKit runtime."""
import sys
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
# Load the backend under an isolated name: the test models UIKit and does not
# require Toga, which is intentionally absent from desktop regression installs.
with patch.dict(sys.modules, {'toga': NS(ImageView=object)}):
    spec = importlib.util.spec_from_file_location('native_magnifier_under_test',
        Path(__file__).resolve().parents[2] / 'ui/native/image_canvas.py')
    canvas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canvas)
    apple_backend = canvas.apple_backend


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
            return NS(alloc=allocate, buttonWithType=lambda kind: allocate(), systemFontOfSize=Mock(),
                      whiteColor=Mock(CGColor=object()), grayColor=Mock(), blackColor=Mock())
        self.modules = patch.dict(sys.modules, {
            'toga_iOS.widgets.imageview': NS(ImageView=ImageView),
            'rubicon.objc': NS(ObjCClass=objc_class, CGRect=rect, CGSize=Mock(),
                               CGPoint=lambda x, y: NS(x=x, y=y), UIEdgeInsets=Mock(), SEL=lambda x: x),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        lens = patch.object(canvas, 'apple_lens_class', return_value=objc_class('UIView'))
        lens.start(); self.addCleanup(lens.stop)
        self.backend = apple_backend(NS(magnifier_enabled=True, magnifier_zoom=200))
        self.backend.lens = self.backend.lens_picture = None
        self.backend.lens_less = self.backend.lens_more = None
        # Model a panned/zoomed page with its origin at (20, 100) in the parent.
        self.backend.picture = NS(image=object(), bounds=rect((0, 0), (200, 300)),
            convertPoint=Mock(side_effect=lambda point, **kw: NS(
                x=(point.x - 20) / 2, y=(point.y - 100) / 2)))
        self.backend.native = Mock(zoomScale=2)
        self.backend.native.superview = NS(addSubview=Mock())
        self.backend.native.convertRect.return_value = rect((0, 0), (400, 800))
        self.backend.hold = NS(enabled=True)

    def gesture(self, image_x=40, image_y=60, thumb_x=100, thumb_y=400):
        return NS(locationInView=lambda target: NS(x=image_x, y=image_y)
                  if target is self.backend.picture else NS(x=thumb_x, y=thumb_y))

    def test_uses_original_pixels_beneath_lens_center_at_current_zoom(self):
        backend = self.backend
        backend.show_magnifier(self.gesture())
        self.assertIs(backend.lens_picture.image, backend.picture.image)
        frame = backend.lens_picture.frame
        self.assertEqual((frame.size.width, frame.size.height), (800, 1200))
        self.assertEqual((frame.origin.x, frame.origin.y), (-70, -390))
        point = backend.picture.convertPoint.call_args.args[0]
        self.assertEqual((point.x, point.y), (100, 330))
        self.assertIs(backend.picture.convertPoint.call_args.kwargs['fromView'], backend.native.superview)
        self.assertEqual(backend.lens.frame.origin.y, 260)
        # Moving keeps the same image and overlay, and clamps to the viewport.
        lens = backend.lens
        backend.show_magnifier(self.gesture(thumb_x=399, thumb_y=10))
        self.assertIs(backend.lens, lens)
        self.assertEqual((lens.center.x, lens.center.y), (310, 70))
        center = backend.lens_picture.center
        self.assertEqual((center.x, center.y), (-268, 870))
        # Motion must not repeatedly resize/reconfigure the native image/buttons.
        self.assertEqual((backend.lens_picture.frame.origin.x, backend.lens_picture.frame.origin.y), (-70, -390))
        backend.lens_less.setEnabled.assert_called_once_with(True)
        backend.lens_more.setEnabled.assert_called_once_with(True)

    def test_lens_over_letterbox_does_not_shift_sample_to_page_edge(self):
        backend = self.backend
        backend.show_magnifier(self.gesture(thumb_y=120))
        self.assertEqual(backend.lens.frame.origin.y, 0)
        # The center is above the page; preserve that blank margin in the lens.
        self.assertEqual(backend.lens_picture.frame.origin.y, 170)

    def test_ignores_initial_letterbox_hold_and_clears_pixels_when_disabled(self):
        backend = self.backend
        backend.show_magnifier(self.gesture(image_x=-10))
        self.assertIsNone(backend.lens)
        backend.show_magnifier(self.gesture())
        lens, picture = backend.lens, backend.lens_picture
        buttons = (backend.lens_less, backend.lens_more)
        backend.set_magnifier_enabled(False)
        self.assertFalse(backend.hold.enabled)
        self.assertIsNone(picture.image)
        lens.removeFromSuperview.assert_called_once()
        for button in buttons:
            button.removeFromSuperview.assert_called_once()
        self.assertIsNone(backend.lens)
        backend.hide_magnifier()  # cancellation/disposal can be repeated

    def test_percentage_updates_original_pixel_transform_and_endpoint_buttons(self):
        backend = self.backend
        backend.interface.magnifier_zoom = 250
        backend.show_magnifier(self.gesture())
        self.assertEqual(backend.lens_picture.frame.size.width, 1000)
        backend.lens_more.setEnabled.assert_called_with(False)
        backend.lens_less.setEnabled.assert_called_with(True)
        self.assertFalse(hasattr(backend, 'lens_label'))
        self.assertEqual((backend.lens_more.frame.size.width, backend.lens_more.frame.size.height), (33, 33))
        self.assertEqual(backend.lens_more.frame.origin.y, backend.lens.frame.origin.y + backend.lens.frame.size.height - 24)
        backend.interface.magnifier_zoom = 150
        backend.hold = self.gesture()
        backend.set_magnifier_zoom(150)
        self.assertEqual(backend.lens_picture.frame.size.width, 600)
        backend.lens_less.setEnabled.assert_called_with(False)
        backend.lens_more.setEnabled.assert_called_with(True)
        self.assertFalse(hasattr(backend, 'lens_label'))
        backend.hide_magnifier()
        self.assertIsNone(backend.lens_more)

    def test_detached_or_disabled_canvas_cannot_show_a_lens(self):
        backend = self.backend
        backend.interface.magnifier_enabled = False
        backend.show_magnifier(self.gesture())
        self.assertIsNone(backend.lens)
        backend.interface.magnifier_enabled = True
        backend.native.superview = None
        backend.show_magnifier(self.gesture())
        self.assertIsNone(backend.lens)


class MagnifierSettingTests(unittest.TestCase):
    def setUp(self):
        self.view = object.__new__(canvas.ImageCanvas)
        self.view._impl = NS(set_magnifier_zoom=Mock())
        self.view._magnifier_zoom = 190
        self.view.on_magnifier_zoom = Mock()

    def test_steps_are_bounded_and_notify_once_per_actual_change(self):
        view = self.view
        for _ in range(10):view.change_magnifier_zoom(1)
        self.assertEqual(view.magnifier_zoom, 250)
        self.assertEqual([call.args[1] for call in view.on_magnifier_zoom.call_args_list], [210,230,250])
        for _ in range(10):view.change_magnifier_zoom(-1)
        self.assertEqual(view.magnifier_zoom, 150)
        for value in (149, 151, 200, 251, '190', 190.0):
            with self.assertRaises(ValueError):view.request_magnifier_zoom(value)

    def test_host_can_reject_a_failed_save_without_changing_native_zoom(self):
        view = self.view
        view.on_magnifier_zoom.return_value = False
        self.assertFalse(view.change_magnifier_zoom(1))
        self.assertEqual(view.magnifier_zoom, 190)
        view._impl.set_magnifier_zoom.assert_not_called()

    def test_lens_passes_touches_through_to_image(self):
        class View:pass
        objc = NS(ObjCClass=lambda name: View, objc_method=lambda method: method, objc_id=object)
        with patch.object(canvas, '_lens_class', None), patch.dict(sys.modules, {
            'rubicon.objc': objc, 'rubicon.objc.types': NS(CGPoint=object),
        }):
            lens = canvas.apple_lens_class()()
        lens.bounds = rect((0,0),(180,140))
        for x,y,expected in ((20,20,False),(160,20,False),(90,20,False),(20,60,False)):
            self.assertEqual(lens.pointInside_withEvent_(NS(x=x,y=y),None),expected)


class LensGeometryTests(unittest.TestCase):
    def test_controls_extend_outside_corners_and_remain_reachable_at_edges(self):
        self.assertEqual(canvas.magnifier_controls_geometry(400, 800, 100, 260, 180), (94, 253, 376))
        self.assertEqual(canvas.magnifier_controls_geometry(400, 800, 0, 0, 180), (0, 153, 116))
        self.assertEqual(canvas.magnifier_controls_geometry(400, 800, 220, 660, 180), (214, 367, 767))
        self.assertEqual(canvas.magnifier_controls_geometry(800, 1200, 200, 400, 360, 280), (194, 533, 656))


    def test_tablets_get_larger_lenses_and_rotation_preserves_size(self):
        phone = canvas.magnifier_geometry(400, 800, 200, 400)
        tablet = canvas.magnifier_geometry(800, 1200, 400, 600)
        rotated = canvas.magnifier_geometry(1200, 800, 600, 400)
        self.assertEqual(phone[2:4], (180, 140))
        self.assertEqual(tablet[2:4], (360, 280))
        self.assertEqual(tablet[2:4], rotated[2:4])

    def test_horizontal_sample_continues_after_lens_stops_at_both_edges(self):
        for start, end in ((80, 0), (320, 400)):
            a = canvas.magnifier_geometry(400, 800, start, 400)
            b = canvas.magnifier_geometry(400, 800, end, 400)
            self.assertEqual(a[0], b[0])
            self.assertEqual((a[4], b[4]), (start, end))

    def test_sample_reaches_all_four_corners_with_lens_inside_viewport(self):
        for width, height in ((400, 800), (800, 1200), (1200, 800), (160, 100)):
            for tx, ty in ((0, 0), (width, 0), (0, height), (width, height)):
                x, y, w, h, sx, sy = canvas.magnifier_geometry(width, height, tx, ty)
                self.assertEqual((sx, sy), (tx, ty))
                self.assertTrue(0 <= x <= width - w)
                self.assertTrue(0 <= y <= height - h)

    def test_vertical_sample_progresses_smoothly_to_bottom(self):
        values = [canvas.magnifier_geometry(800, 1200, 400, y)[5] for y in range(1201)]
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 1200)
        self.assertTrue(all(0 <= b-a <= 2 for a, b in zip(values, values[1:])))


class AppleHoldLifecycleTests(unittest.TestCase):
    def test_release_cancel_pinch_and_detach_clear_the_lens(self):
        image_canvas = canvas
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
