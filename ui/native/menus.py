"""Native button menus; hosts own command guards, scheduling and fallback UI."""


class NativeMenu:
    def __init__(self, button, actions, *, invoke, context, fallback):
        self.button, self.actions = button, tuple(actions)
        self.invoke_callback, self.context, self.fallback = invoke, context, fallback
        self.blocks, self.listener, self.popup = [], None, None
        self.disposed = False
        backend = type(button._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            native_actions = []
            for title, callback in self.actions:
                def dispatch(action, target=callback):
                    self.invoke(target)
                block = Block(dispatch, None, objc_id)
                self.blocks.append(block)
                native_actions.append(ObjCClass('UIAction').actionWithTitle(title,
                    image=None, identifier=None, handler=block))
            button._impl.native.menu = ObjCClass('UIMenu').menuWithTitle('', children=native_actions)
            button._impl.native.showsMenuAsPrimaryAction = True
        else:
            button.on_press = self.show

    def invoke(self, callback):
        if not self.disposed:
            return self.invoke_callback(callback)

    def show(self, widget=None, **kwargs):
        if self.disposed:
            return
        if type(self.button._impl).__module__.startswith('toga_android.'):
            from android.widget import PopupMenu
            from java import dynamic_proxy
            context = self.context()
            if context is None:
                return
            self.popup = PopupMenu(context, self.button._impl.native)
            menu = self
            class Listener(dynamic_proxy(PopupMenu.OnMenuItemClickListener)):
                def onMenuItemClick(self, item):
                    if not menu.disposed:
                        menu.invoke(menu.actions[item.getItemId()][1])
                    return True
            self.listener = Listener()
            for index, (title, callback) in enumerate(self.actions):
                self.popup.getMenu().add(0, index, index, title)
            self.popup.setOnMenuItemClickListener(self.listener)
            self.popup.show()
        else:
            return self.fallback()

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        if self.popup is not None:
            self.popup.dismiss()
            self.popup.setOnMenuItemClickListener(None)
        if type(self.button._impl).__module__.startswith('toga_iOS.'):
            self.button._impl.native.menu = None
            self.button._impl.native.showsMenuAsPrimaryAction = False
        else:
            self.button.on_press = None
        self.blocks.clear()
        self.listener = self.popup = None
        self.actions = ()
        self.invoke_callback = self.context = self.fallback = None
