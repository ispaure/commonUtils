# Working with shared components

commonUtils is embedded by an application. The host chooses which controls
appear, which folders are accessible and where documents are saved. This guide
explains shared behavior; the host's guide supplies its buttons and account setup.

## Browse first, then choose a search

The live file list shows the current folder. Indexed search and folder sizes use
saved metadata and may lag behind it. If a visible file is absent from search,
check whether indexing has unfinished folders. Where offered, **Index details…**
explains errors and **Refresh index** checks the current subtree. Name search
does not search document contents.

Start a broad search at the parent folder that should contain the result. Opening
a matching child folder narrows its scope. An unavailable drive/network location
may need reconnection before refresh. Saved metadata is not a backup of contents.
The [File Browser guide](file_browser/file_browser.md) explains matching and views;
the [native browser guide](native_browser/native_browser.md) covers related mobile
controls. Hosts can restrict their actions.

## Keep both versions when a save conflicts

A conflict means the saved file and the editor's opening baseline no longer agree.
Keep the editor open while inspecting the other version. If the host offers
Save As or export, preserve your draft elsewhere before choosing a version.
Repeated Save does not resolve the underlying conflict.

Changing a file, closing a tab or opening another document may invoke a save/discard
prompt. Cancelling keeps the document open. A failed save is not a successful
close. Recovery and private-document storage are host policies; not every embedded
editor writes a draft to disk.

Use the [Markdown guide](markdown/markdown.md) for formatted/source editing and
the [code editor guide](code_editor/code_editor.md) for source and merge tools.

## Cancel, then inspect what finished

Cancellation is cooperative. Some batches finish their current file before
stopping; other operations check between stream chunks. The host retains the
progress owner while workers retire, so closing a window can take time.

Read the result before retrying. Completed items may remain, and failed cleanup
does not necessarily undo publication. Refresh the destination and preserve the
originals until you know which items succeeded. Archive extraction and file
replacement have different publication rules, described by the host's action
guide. The [archive guide](archive_view/archive_view.md) covers browsing; a listing
does not prove every encrypted member can be decoded or extracted.

## Recognize host restrictions

A read-only browser intentionally omits mutation actions. Remote/private items
need not be ordinary filesystem paths. A missing action can mean the host has
not granted a capability. After locking credentials or replacing a provider,
reopen through the host storage view; a retained window cannot restore access.

For a useful problem report, include the application version, component,
operation, local/private/remote source type and visible error. Use a disposable
example. Exclude passwords, tokens and private document contents.

[Component user guides](user.md)
