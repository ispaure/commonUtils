"""Keep Toga's reusable UITableView cells, adding browser row semantics."""
from rubicon.objc import objc_method, ObjCInstance, ObjCBlock
from toga_iOS.widgets.detailedlist import DetailedList, TogaTableViewController
from toga_iOS.libs import UITableViewCell, UITableViewCellStyleSubtitle, UIView

_row_action_type = None
_file_cell_type = None


def _superview(view):
    parent = view.superview
    return parent() if callable(parent) else parent


def _layout_action_labels(cell):
    """Use a small visual gap instead of UIKit's accessory gutter."""
    button = cell.accessoryView
    if button is None:
        return
    from rubicon.objc import CGRect
    trailing = 4
    view = _superview(cell)
    while view is not None:
        if hasattr(view, 'showsVerticalScrollIndicator'):
            indicator = view.showsVerticalScrollIndicator
            indicator = indicator() if callable(indicator) else indicator
            if indicator and view.contentSize.height > view.bounds.size.height:
                trailing = 8
            break
        view = _superview(view)
    frame = button.frame
    button_x = max(0, float(cell.bounds.size.width) - float(cell.safeAreaInsets.right)
                   - trailing - float(frame.size.width))
    button.frame = CGRect((button_x, frame.origin.y),
                          (frame.size.width, frame.size.height))
    content = cell.contentView
    frame = content.frame
    right = button_x - float(frame.origin.x) - 4
    content.frame = CGRect((frame.origin.x, frame.origin.y),
                           (max(0, right), frame.size.height))
    for label in (cell.textLabel, cell.detailTextLabel):
        frame = label.frame
        label.frame = CGRect((frame.origin.x, frame.origin.y),
                             (max(0, right - float(frame.origin.x)), frame.size.height))


def _new_file_cell():
    global _file_cell_type
    if _file_cell_type is None:
        from rubicon.objc import send_super
        class CommonUtilsFileCell(UITableViewCell):
            @objc_method
            def layoutSubviews(self) -> None:
                send_super(__class__, self, 'layoutSubviews')
                _layout_action_labels(self)
        _file_cell_type = CommonUtilsFileCell
    return _file_cell_type.alloc().initWithStyle(
        UITableViewCellStyleSubtitle, reuseIdentifier='file-row')


def _bind_actions(interface, cell, row):
    """A visible contextual control; a normal row tap continues to open."""
    apple_color = interface.appearance.apple_color
    if (not getattr(interface, '_primary_action', None)
            or not getattr(getattr(interface, '_impl', None), 'primary_action_enabled', False)):
        cell.accessoryView = None
        return
    global _row_action_type
    from rubicon.objc import ObjCClass, objc_property, SEL, CGRect, CGPoint, Block, objc_id, ns_from_py
    import weakref
    if _row_action_type is None:
        class FileRowAction(ObjCClass('UIButton')):
            owner = objc_property(object)
            row = objc_property(object)
            menu_provider_block = objc_property(object)

            @objc_method
            def pointInside_withEvent_(self, point: CGPoint, event: ObjCInstance) -> bool:
                # Give the dots priority over the end of the filename, retaining
                # a row-height-wide target without reserving that much text space.
                bounds = self.bounds
                inset = max(0, float(bounds.size.height) - float(bounds.size.width))
                return (-inset <= point.x <= float(bounds.size.width)
                        and 0 <= point.y <= float(bounds.size.height))

            @objc_method
            def selectRow_(self, sender) -> None:
                owner, row = self.owner(), self.row
                if (owner is not None and owner.enabled and row is not None
                        and row.index < len(owner.data) and owner.data[row.index] is row):
                    if getattr(owner, 'menu_provider', None) is None:
                        owner.on_primary_action(row=row)
        _row_action_type = FileRowAction
    button = cell.accessoryView
    if button is None:
        height = interface.appearance.row_height
        button = _row_action_type.alloc().initWithFrame(CGRect((0, 0), (min(28, height), height)))
        button.setTitle('⋯', forState=0)
        button.titleLabel.font = ObjCClass('UIFont').systemFontOfSize(24)
        button.addTarget(button, action=SEL('selectRow:'), forControlEvents=1 << 6)
        cell.accessoryView = button
    button.owner, button.row = weakref.ref(interface), row
    if getattr(interface, 'menu_provider', None) is not None:
        # Resolve on every opening: reusable cells must never cache another
        # row's commands or a previous credential generation.
        def provide(completion):
            completion = ObjCInstance(completion).copy()
            owner = button.owner()
            current = button.row
            async def load():
                # ObjCBlock stores only a pointer. Keep the copied Objective-C
                # owner in this coroutine until the asynchronous load completes.
                complete = ObjCBlock(completion, None, objc_id)
                if (owner is None or not owner.enabled or current is None or button.row is not current
                        or current.index >= len(owner.data) or owner.data[current.index] is not current):
                    complete(ns_from_py([]))
                    return
                try:
                    children = await owner.menu_provider(current)
                    complete(ns_from_py(children if button.row is current else []))
                except Exception:
                    complete(ns_from_py([]))
                    raise
            import toga
            toga.App.app.loop.create_task(load())
        button.menu_provider_block = Block(provide, None, objc_id)
        deferred = ObjCClass('UIDeferredMenuElement').elementWithUncachedProvider(button.menu_provider_block)
        button.menu = ObjCClass('UIMenu').menuWithTitle('', children=[deferred])
        button.showsMenuAsPrimaryAction = True

    button.accessibilityLabel = interface._primary_action + ' ' + row.title
    button.setTitleColor(apple_color('accent'), forState=0)
    button.enabled = interface.enabled
    cell.isAccessibilityElement = False


def _clear_actions(cell):
    button = getattr(cell, 'accessoryView', None)
    if button is not None:
        button.row = None
        button.menu = None
        button.showsMenuAsPrimaryAction = False
        button.menu_provider_block = None
        button.accessibilityLabel = ''


def _bind_separator(cell, *, last, color):
    """Own the between-row line without changing UIKit's text layout insets."""
    from rubicon.objc import CGRect
    content = cell.contentView
    line = content.viewWithTag(7421)
    if line is None:
        line = UIView.alloc().init()
        line.tag = 7421
        line.setUserInteractionEnabled(False)
        # Flexible width and top margin keep the line at the row's bottom.
        line.autoresizingMask = 2 | 8
        content.addSubview(line)
    line.frame = CGRect((12, max(0, float(content.bounds.size.height) - 1)),
                        (max(0, float(content.bounds.size.width) - 24), 1))
    line.backgroundColor = color
    line.setHidden(last)


def _bind_file_cell(interface, cell, index):
    apple_color = interface.appearance.apple_color
    from rubicon.objc import UIEdgeInsets
    row = interface.data[index]
    cell.textLabel.text = row.title
    cell.detailTextLabel.text = row.subtitle
    cell.imageView.image = row.icon._impl.native if row.icon is not None else None
    cell.accessoryType = 1 if row.folder else 0
    cell.textLabel.lineBreakMode = 5  # Middle truncation preserves extensions.
    cell.accessibilityLabel = row.title + ('. Folder' if row.folder else '. ' + interface.row_kind)
    cell.backgroundColor = apple_color('surface')
    # Only the outer corners belong to the group; recycled middle cells must
    # lose any corner mask left over from a previous first/last row.
    cell.layer.cornerRadius = 16
    cell.layer.maskedCorners = (3 if index == 0 else 0) | (12 if index == len(interface.data) - 1 else 0)
    cell.layer.masksToBounds = True
    # UIKit also uses the separator's leading inset to lay out cell content.
    # Use the outer gutter here; adding an icon slot shifts the image and text
    # a second time. The image's point size already reserves its own space.
    cell.preservesSuperviewLayoutMargins = False
    cell.layoutMargins = UIEdgeInsets(0, 12, 0, 12)
    cell.separatorInset = UIEdgeInsets(0, 12, 0, 12)
    _bind_separator(cell, last=index == len(interface.data) - 1, color=apple_color('border'))
    cell.textLabel.textColor = apple_color('muted' if getattr(row, 'hidden', False) else 'text')
    cell.textLabel.highlightedTextColor = cell.textLabel.textColor
    cell.detailTextLabel.textColor = apple_color('muted')
    _bind_actions(interface, cell, row)
    interface.row_visible(index)
    # A cached visible-row callback may have supplied its image synchronously.
    cell.imageView.image = row.icon._impl.native if row.icon is not None else None


class FileTableController(TogaTableViewController):
    @objc_method
    def gestureRecognizerShouldBegin_(self, gesture) -> bool:
        return (self.interface.enabled and self.impl.primary_action_enabled
                and getattr(self.interface, 'menu_provider', None) is None)

    @objc_method
    def holdRow_(self, gesture) -> None:
        # Resolve the live cell when the hold begins; never keep a recycled index.
        if gesture.state != 1 or not self.interface.enabled:
            return
        path = self.tableView.indexPathForRowAtPoint(gesture.locationInView(self.tableView))
        if path is None:
            return
        cell = self.tableView.cellForRowAtIndexPath(path)
        button = cell.accessoryView if cell is not None else None
        if button is not None and getattr(self.interface, 'menu_provider', None) is None:
            button.selectRow_(button)

    @objc_method
    def tableView_didEndDisplayingCell_forRowAtIndexPath_(self, tableView, cell, indexPath):
        # A delayed retirement notification can arrive after UIKit has already
        # associated this reusable cell with a live row. Never erase that row.
        if tableView.indexPathForCell(cell) is not None:
            return
        cell.textLabel.text = ''
        cell.detailTextLabel.text = ''
        cell.imageView.image = None
        cell.accessibilityLabel = ''
        _clear_actions(cell)

    @objc_method
    def tableView_willDisplayCell_forRowAtIndexPath_(self, tableView, cell, indexPath):
        # Restoring the window root after unlocking can redisplay a retained
        # cell without asking cellForRowAtIndexPath to populate it again.
        _bind_file_cell(self.interface, cell, indexPath.row)

    @objc_method
    def tableView_cellForRowAtIndexPath_(self, tableView, indexPath):
        cell = tableView.dequeueReusableCellWithIdentifier('file-row')
        if cell is None:
            cell = _new_file_cell()
            selection = UIView.alloc().init()
            selection.backgroundColor = self.interface.appearance.apple_color('hover')
            cell.selectedBackgroundView = selection
        _bind_file_cell(self.interface, cell, indexPath.row)
        return cell


class IOSFileList(DetailedList):
    def change_source(self, source):
        # UIKit queries row count when the footer is assigned. Wait until Toga
        # has published its initial data source instead of doing this in create.
        if self.native.tableFooterView is None:
            self.native.tableFooterView = UIView.alloc().init()
        super().change_source(source)

    def set_enabled(self, enabled):
        self.native.userInteractionEnabled = bool(enabled)

    def source_change(self, *, item):
        if item.index >= len(self.interface.data) or self.interface.data[item.index] is not item:
            return
        from toga_iOS.libs import NSIndexPath
        cell = self.native.cellForRowAtIndexPath(NSIndexPath.indexPathForRow(item.index, inSection=0))
        if cell is not None:
            cell.imageView.image = item.icon._impl.native if item.icon is not None else None
            cell.setNeedsLayout()

    def get_vertical_position(self):
        return max(0, float(self.native.contentOffset.y + self.native.adjustedContentInset.top))

    def get_max_vertical_position(self):
        self.native.layoutIfNeeded()
        return max(0, float(self.native.contentSize.height - self.native.bounds.size.height
                            + self.native.adjustedContentInset.top + self.native.adjustedContentInset.bottom))

    def set_vertical_position(self, value):
        from rubicon.objc import CGPoint
        self.native.layoutIfNeeded()
        position = min(max(0, value), self.get_max_vertical_position())
        self.native.setContentOffset(CGPoint(self.native.contentOffset.x,
            position - self.native.adjustedContentInset.top), animated=False)

    def primary_action_handler(self, index):
        row = self.interface.data[index]
        def selected(action: ObjCInstance, view: ObjCInstance, completion: ObjCInstance) -> None:
            self.interface.on_primary_action(row=row)
            ObjCBlock(completion, None, bool)(True)
        return selected

    def create(self):
        # Same Toga backend contract, with a UITableViewController subclass.
        self.native_controller = FileTableController.alloc().init()
        self.native_controller.interface = self.interface
        self.native_controller.impl = self
        self.native = self.native_controller.tableView
        # The destination container already lays out below the navigation bar.
        # A retained parent table can inherit UIKit's full bar inset during a
        # pop, briefly shifting its rows down before the live browser returns.
        self.native.contentInsetAdjustmentBehavior = 2  # Never
        self.native.delegate = self.native_controller
        from rubicon.objc import ObjCClass, SEL
        self.hold_gesture = ObjCClass('UILongPressGestureRecognizer').alloc().initWithTarget(
            self.native_controller, action=SEL('holdRow:'))
        self.hold_gesture.delegate = self.native_controller
        self.native.addGestureRecognizer(self.hold_gesture)
        self.native.rowHeight = self.interface.appearance.row_height
        self.native.keyboardDismissMode = 1
        from rubicon.objc import UIEdgeInsets
        self.native.backgroundColor = self.interface.appearance.apple_color('transparent')
        self.native.separatorColor = self.interface.appearance.apple_color('transparent')
        self.native.separatorStyle = 0  # App-owned lines only between rows.
        self.native.separatorInset = UIEdgeInsets(0, 12, 0, 12)
        self.primary_action_enabled = self.secondary_action_enabled = False
        self.add_constraints()

    def prepare_source_change(self):
        # Inspect visible cells before the interface replaces its source. Asking
        # UIKit for them afterward can bind old indexes against the new source.
        if self.native.window is None:
            return
        for cell in self.native.visibleCells:
            cell.textLabel.text = ''
            cell.detailTextLabel.text = ''
            cell.imageView.image = None
            cell.accessibilityLabel = ''
            _clear_actions(cell)
        selected = self.native.indexPathForSelectedRow
        if selected is not None:
            self.native.deselectRowAtIndexPath(selected, animated=False)
