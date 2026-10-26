# Anchor-relative dock placement

`workspace_layout.split_at` is an internal Workspace helper. Native Qt may tabify
instead of splitting a tabified anchor, even after its companions are removed.
Removing/re-adding that anchor also loses its original layout slot.

The helper captures visible groups, tab order, active tabs and rectangles; finds
the existing horizontal/vertical partition; inserts the new left/right leaf; and
rebuilds native splits before restoring tabification. It retains existing widget
instances. Adjacent partitions on the same axis are flattened before sizing, so
resizing the split target does not resize unrelated columns. Intermediate view
activation is suppressed. Workspace adoption retains its existing rollback path.
Center adoption uses the supplied target anchor, including transfers from another
container. Left/right describe physical screen placement in either layout direction.

Regression tests assert actual rectangles, repeated physical ordering, neighboring
widths, nested vertical partitions, reordered tab companions and center transfers.
