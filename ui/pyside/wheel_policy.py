"""Reserve wheel gestures for scrolling instead of changing form values."""

from ._imports import (
    QObject, QWidget, QEvent, QApplication, QAbstractSpinBox, QComboBox,
    QSlider, QDial, QAbstractScrollArea, QScrollArea, QWheelEvent, QPointF,
)


class ValueWheelPolicy(QObject):
    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False
        # Spin boxes and editable combos receive some events through their
        # embedded line edit. Forward to the containing scroll area explicitly;
        # filtering a wheel event alone does not make Qt propagate it there.
        widget = watched
        while widget is not None:
            if isinstance(widget, (QAbstractSpinBox, QComboBox, QSlider, QDial)):
                parent = widget.parentWidget()
                while parent is not None:
                    if isinstance(parent, QAbstractScrollArea):
                        # QScrollArea's scrollbar handler in Qt 6.6 uses angle
                        # deltas only. Preserve pixel-only trackpad scrolling.
                        pixels = event.pixelDelta()
                        if isinstance(parent, QScrollArea) and not pixels.isNull():
                            for bar, delta in (
                                (parent.horizontalScrollBar(), pixels.x()),
                                (parent.verticalScrollBar(), pixels.y()),
                            ):
                                if bar.isEnabled() and delta:
                                    bar.setValue(bar.value() - delta)
                            break
                        viewport = parent.viewport()
                        forwarded = QWheelEvent(
                            QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                            event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                            event.buttons(), event.modifiers(), event.phase(), event.inverted(),
                            event.source(), event.pointingDevice(),
                        )
                        QApplication.sendEvent(viewport, forwarded)
                        break
                    if parent.isWindow():
                        break
                    parent = parent.parentWidget()
                event.ignore()
                return True
            if widget.isWindow():
                break
            widget = widget.parentWidget()
        # A combo's popup is a separate window: its list still scrolls normally.
        return False


def install_value_wheel_policy(app=None):
    """Install once per app, including existing and directly imported Qt widgets."""
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError('Create QApplication before installing value wheel policy')
    policy = getattr(app, '_commonutils_value_wheel_policy', None)
    if policy is None:
        policy = app._commonutils_value_wheel_policy = ValueWheelPolicy(app)
        app.installEventFilter(policy)
    return policy
