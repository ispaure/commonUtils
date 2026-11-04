"""Optional tree metadata and local drag actions for reusable UIKit file cells."""
import weakref

from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property, ns_from_py, SEL, CGRect
from rubicon.objc.types import NSInteger


def current(owner, row):
    interface = owner() if owner is not None else None
    if (interface is None or not interface.enabled or interface.updating or row is None
            or not 0 <= row.index < len(interface.data) or interface.data[row.index] is not row):
        return None
    actions = getattr(interface, 'tree_actions', None)
    return (interface, actions) if actions is not None and actions.current(row) else None


def _new_delegate(kind, interface, row, *, cell=None):
    delegate = kind.alloc()
    delegate.owner, delegate.row = weakref.ref(interface), row
    if cell is not None:
        delegate.cell = cell
    return delegate.init()


class TreeDisclosure(ObjCClass('UIButton')):
    owner = objc_property(object)
    row = objc_property(object)

    @objc_method
    def toggle_(self, sender) -> None:
        target = current(self.owner, self.row)
        if target is not None:
            target[1].toggle(self.row)


class TreeDrag(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIDragInteractionDelegate'),)):
    owner = objc_property(object)
    row = objc_property(object)

    @objc_method
    def dragInteraction_itemsForBeginningSession_(self, interaction, session):
        target = current(self.owner, self.row)
        if target is None or not target[1].start_drag(self.row):
            return ns_from_py([])
        token = target[1].drag_token
        session.localContext = ns_from_py(token)
        provider = ObjCClass('NSItemProvider').alloc().initWithObject(ns_from_py(token))
        item = ObjCClass('UIDragItem').alloc().initWithItemProvider(provider)
        item.localObject = ns_from_py(token)
        return ns_from_py([item])

    @objc_method
    def dragInteraction_sessionIsRestrictedToDraggingApplication_(self, interaction, session) -> bool:
        return True

    @objc_method
    def dragInteraction_session_didEndWithOperation_(self, interaction, session, operation: NSInteger) -> None:
        interface = self.owner() if self.owner is not None else None
        actions = getattr(interface, 'tree_actions', None)
        if actions is not None:
            actions.end_drag()


class TreeDrop(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIDropInteractionDelegate'),)):
    owner = objc_property(object)
    row = objc_property(object)
    cell = objc_property(object)

    def target(self, session):
        target = current(self.owner, self.row)
        local = session.localDragSession
        return (target if target is not None and local is not None and
                str(local.localContext) == target[1].drag_token else None)

    def paint(self, active=False):
        interface = self.owner() if self.owner is not None else None
        if self.cell is not None and interface is not None:
            self.cell.backgroundColor = interface.appearance.apple_color('hover' if active else 'surface')

    @objc_method
    def dropInteraction_canHandleSession_(self, interaction, session) -> bool:
        return self.target(session) is not None

    @objc_method
    def dropInteraction_sessionDidUpdate_(self, interaction, session):
        target = self.target(session)
        allowed = target is not None and self.row.folder and target[1].can_drop(self.row)
        self.paint(allowed)
        return ObjCClass('UIDropProposal').alloc().initWithDropOperation(3 if allowed else 1)

    @objc_method
    def dropInteraction_performDrop_(self, interaction, session) -> None:
        target = self.target(session)
        if target is not None and self.row.folder:
            target[1].drop(self.row)
        self.paint()

    @objc_method
    def dropInteraction_sessionDidExit_(self, interaction, session) -> None:
        self.paint()

    @objc_method
    def dropInteraction_sessionDidEnd_(self, interaction, session) -> None:
        interface = self.owner() if self.owner is not None else None
        actions = getattr(interface, 'tree_actions', None)
        if actions is not None:
            actions.end_drag()
        self.paint()


def clear(cell):
    if getattr(cell, 'tree_owner', None) is None:
        return
    cell.tree_owner = cell.tree_row = None
    cell.textLabel.attributedText = None
    button = cell.tree_disclosure
    if button is not None:
        button.owner = button.row = None
        button.accessibilityLabel = ''
        button.setHidden(True)
    for binding in (cell.tree_drag, cell.tree_drop):
        if binding is not None:
            interaction, delegate = binding
            delegate.owner = delegate.row = None
            if isinstance(delegate, TreeDrop):
                delegate.cell = None


def bind(interface, cell, row):
    if getattr(interface, 'tree_actions', None) is None:
        return
    cell.tree_owner, cell.tree_row = weakref.ref(interface), row
    cell.accessoryType = 0  # Folder disclosure is separate from the action slot.
    cell.indentationLevel = 0
    expanded = getattr(row, 'tree_expanded', None)
    if expanded is not None and cell.tree_disclosure is None:
        button = TreeDisclosure.alloc()
        button.owner, button.row = weakref.ref(interface), row
        button = button.initWithFrame(CGRect((0, 0), (44, interface.appearance.row_height)))
        button.titleLabel.font = ObjCClass('UIFont').systemFontOfSize(22)
        button.addTarget(button, action=SEL('toggle:'), forControlEvents=1 << 6)
        cell.contentView.addSubview(button)
        cell.tree_disclosure = button
        tap = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget(button, action=SEL('toggle:'))
        cell.imageView.addGestureRecognizer(tap)
        cell.tree_icon_tap = tap
    if cell.tree_disclosure is not None:
        button = cell.tree_disclosure
        button.owner, button.row = weakref.ref(interface), row
        button.setHidden(expanded is None)
        button.enabled = interface.enabled
        button.setTitle('⌄' if expanded else '›', forState=0)
        button.accessibilityLabel = ('Collapse ' if expanded else 'Expand ') + row.title
        button.setTitleColor(interface.appearance.apple_color('muted'), forState=0)
    landing = bool(getattr(row, 'tree_landing', False))
    cell.textLabel.attributedText = (ObjCClass('NSAttributedString').alloc().initWithString(row.title,
        attributes={'NSUnderline': 1, 'NSFont': cell.textLabel.font, 'NSColor': cell.textLabel.textColor})
        if landing else None)
    if not landing:
        cell.textLabel.text = row.title
    icons = getattr(interface, '_tree_icons', None)
    if icons is None:
        interface._tree_icons = icons = {}
    key = 'landing' if landing else row.folder
    if key not in icons:
        from .recycled_list import thumbnail_image
        image = (getattr(interface, 'tree_landing_icon', None) if landing else
                 interface.appearance.icon(row.folder))
        icons[key] = thumbnail_image(image, size=interface.appearance.icon_size) if image is not None else None
    image = icons[key]
    cell.imageView.image = image._impl.native if image is not None else None
    cell.imageView.userInteractionEnabled = True
    if cell.tree_drag is None:
        delegate = _new_delegate(TreeDrag, interface, row)
        interaction = ObjCClass('UIDragInteraction').alloc().initWithDelegate(delegate)
        interaction.enabled = True
        cell.imageView.addInteraction(interaction)
        cell.tree_drag = (interaction, delegate)
    if cell.tree_drop is None:
        delegate = _new_delegate(TreeDrop, interface, row, cell=cell)
        interaction = ObjCClass('UIDropInteraction').alloc().initWithDelegate(delegate)
        cell.addInteraction(interaction)
        cell.tree_drop = (interaction, delegate)
    for interaction, delegate in (cell.tree_drag, cell.tree_drop):
        delegate.owner, delegate.row = weakref.ref(interface), row
    cell.tree_drop[1].cell = cell
    layout(cell)


def layout(cell):
    row = getattr(cell, 'tree_row', None)
    owner = getattr(cell, 'tree_owner', None)
    interface = owner() if owner is not None else None
    if row is None or interface is None:
        return
    left = 12 + min(32, max(0, row.tree_depth)) * 12
    height = float(cell.bounds.size.height)
    size = interface.appearance.icon_size
    cell.imageView.frame = CGRect((left, (height - size) / 2), (size, size))
    left += size + 4
    if getattr(row, 'tree_expanded', None) is not None:
        cell.tree_disclosure.frame = CGRect((left, 0), (44, height))
        left += 44
    right = float(cell.contentView.bounds.size.width) - 4
    for label in (cell.textLabel, cell.detailTextLabel):
        frame = label.frame
        label.frame = CGRect((left, frame.origin.y), (max(0, right - left), frame.size.height))
