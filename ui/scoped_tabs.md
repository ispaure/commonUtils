# Project-confined tab gestures

`ScopedTabBar(group, boundary, groups, move_tab)` provides internal moves for
QTabWidgets without registering them with the application workspace drag system.
The host supplies its live group list and owns document transfers, split limits,
close prompts and empty-group cleanup. The callback receives the view, target
group, placement (`left`, `tabs`, `right`) and insertion index. Header drops reorder
or insert; content drops use the same quarter/center/quarter geometry as Workspace.
Drops outside the boundary and Escape cancel. No gesture creates a native window.
Keep QTabWidget's built-in movable mode disabled when using this bar.

The bar observes application mouse events only during an armed tab gesture.
Moves/releases delivered to another child widget still finish the originating
gesture once, using global coordinates translated to the source bar. Normal
clicks keep Qt's tab selection behavior. Preview targets continue updating after
the drag threshold is crossed, including when the pointer returns near its start.
Escape, hiding the source/boundary, window deactivation, or movement without the
left button clears the observer and preview. Release revalidates the live target
with the host's optional `can_move` callback before calling `move_tab`.

Workspace keeps a single header if hiding it would remove the only new-tab control
(a view without `workspace_controls`). Views with a controls layout can continue
hiding their detached single header. Buttons resolve the current dock owner at
click time. Tab reordering now emits `tabs_changed` for host persistence.

An optional `can_move(view, target, placement, index)` callback suppresses invalid
snap previews. The complete header strip accepts insertion, including its empty
space. Preview bands belong to tab widgets, never to the boundary QSplitter:
Qt automatically registers direct QWidget children as panes. Cancellation reparents
the preview to its source before a move can dispose of the target group.
