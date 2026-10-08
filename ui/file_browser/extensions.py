"""Compile a feature declaration into a reversible per-window browser layer."""

from ...filesystem import BrowserAction
from ...features import ActionContext, resolve_type
from .. import pyside as qt


class InstalledFeature(qt.QObject):
    idle = qt.Signal()

    def __init__(self, feature, browser, *, host=None, controller=None):
        super().__init__(browser)
        self.feature = feature
        self.browser = browser
        self.host = host if host is not None else browser.window()
        extension = feature.browser
        self._actions = tuple((action, tuple(resolve_type(kind) for kind in action.accepts))
                              for action in extension.actions)
        self._activation = tuple((entry, tuple(resolve_type(kind) for kind in entry.accepts))
                                 for entry in extension.activation)
        self.controller = controller
        if self.controller is None and extension.create_controller is not None:
            self.controller = extension.create_controller(self.host)
        idle = getattr(self.controller, 'idle', None)
        if idle is not None:
            idle.connect(self.idle.emit)
        self.enabled = feature.enabled
        browser.install_extension(feature.id, action_providers=(self._actions_for,),
            activation_handlers=(self._activate,) if self._activation else (),
            folder_fields=extension.folder_fields, enabled=self.enabled)
        self.destroyed.connect(lambda: feature._bindings.discard(self))

    def _context(self, selection):
        return ActionContext(self.browser, self.host, self.controller, tuple(selection))

    def _actions_for(self, item, context):
        return tuple(BrowserAction(f'{self.feature.id}.{action.id}', action.label,
            lambda ctx, action=action, accepts=accepts: self._invoke(action, accepts, ctx), source=self.feature.label)
            for action, accepts in self._actions if isinstance(item, accepts)
            and (action.is_available is None or action.is_available(self._context((item,)))))

    def _invoke(self, action, accepts, context):
        if not self.enabled:
            raise RuntimeError(f'{self.feature.label} is disabled')
        selection = tuple(item for item in context.selection if isinstance(item, accepts))
        if not selection:
            raise ValueError('The selection contains no supported files or folders')
        return action.handler(self._context(selection))

    def _activate(self, item, context):
        if not self.enabled:
            return False
        for activation, accepts in self._activation:
            if isinstance(item, accepts):
                activation.handler(self._context((item,)))
                return True
        return False

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.browser.set_extension_enabled(self.feature.id, self.enabled)

    def prepare_close(self):
        prepare = getattr(self.controller, 'prepare_close', None)
        return prepare() if callable(prepare) else True

    def remove(self):
        """Detach capabilities; the host still owns any controller with running work."""
        self.enabled = False
        self.browser.remove_extension(self.feature.id)
        self.feature._bindings.discard(self)
