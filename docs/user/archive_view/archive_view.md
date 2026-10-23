# Browsing archive contents

The shared archive view presents entries supplied by your application. It lets you
navigate internal folders, filter member names and inspect previews. Opening an
archive, passwords, extraction destinations and modifying the archive are controlled
by the application hosting the view.

Choose a folder in the folder tree, or double-click a folder in the entry list.
Use Parent folder (Alt+Up) to move upward. Filtering matches member paths without
case sensitivity across the supplied contents; clear it to resume folder navigation.
Sort columns to compare sizes numerically. Missing packed sizes or dates appear as
unknown rather than being invented for the archive format.

Select one file and choose **Preview file**, or double-click it. The application
loads a text/image preview and can report unsupported, encrypted or unreadable content.
Selecting multiple items shows selection details; preview requires one file.
Previews do not imply a permanent extraction has occurred.

**Extract selected…** requests extraction from the host. **Remove from ZIP…** appears
only when the host enables editing. Destination, password, confirmation and error
handling follow that application's workflow. Controls can be disabled while work
is running or the view is closing. The shared contents view alone cannot carry out
these requests.

If no contents appear, open an archive through the host first. If a preview is empty,
select one file and check the host's reported result. For extraction or password
problems consult the application's archive workflow rather than changing view settings.

[Developer integration](../../reference/ui/archive_view/archive_view.md) · [All shared guides](../../overview.md#shared-component-user-guides)
