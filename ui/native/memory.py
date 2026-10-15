"""Isolated native memory-pressure subscriptions with explicit disposal."""
import weakref


class MemoryPressure:
    def __init__(self, app, *, on_pressure, on_configuration=None):
        self.app = weakref.ref(app)
        self.disposed = False
        self.callbacks = {}
        for name, callback in [('pressure', on_pressure), ('configuration', on_configuration)]:
            if callback is not None:
                self.callbacks[name] = (weakref.WeakMethod(callback) if getattr(callback, '__self__', None) is not None
                                        else lambda callback=callback: callback)
        self.observer = self.listener = self.context = self.block = None
        backend = type(app._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            self.center = ObjCClass('NSNotificationCenter').defaultCenter
            self.block = Block(lambda notification: self.release(), None, objc_id)
            self.observer = self.center.addObserverForName('UIApplicationDidReceiveMemoryWarningNotification',
                object=None, queue=None, usingBlock=self.block)
        elif backend.startswith('toga_android.'):
            from android.content import ComponentCallbacks2
            from java import dynamic_proxy
            subscription = self
            class Listener(dynamic_proxy(ComponentCallbacks2)):
                def onConfigurationChanged(self, configuration):
                    subscription.dispatch('configuration')
                def onLowMemory(self):
                    subscription.release()
                def onTrimMemory(self, level):
                    if level >= 10:
                        subscription.release()
            self.listener = Listener()
            self.context = app._impl.native.getApplicationContext()
            self.context.registerComponentCallbacks(self.listener)

    def dispatch(self, name):
        app = self.app()
        if self.disposed or app is None or name not in self.callbacks:
            return
        def invoke():
            callback = self.callbacks.get(name)
            callback = callback() if callback is not None else None
            if not self.disposed and self.app() is not None and callback is not None:
                callback()
        app.loop.call_soon_threadsafe(invoke)

    def release(self):
        self.dispatch('pressure')

    def dispose(self):
        self.disposed = True
        self.callbacks.clear()
        if self.observer is not None:
            self.center.removeObserver(self.observer)
            self.observer = self.block = None
        if self.listener is not None:
            self.context.unregisterComponentCallbacks(self.listener)
            self.listener = self.context = None
