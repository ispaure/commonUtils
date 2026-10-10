# Desktop UI

Shared desktop widgets and optional dialog backends. Use a QApplication before
Qt widgets; applications retain their own document, job and close policies.

| Area | Guide |
| --- | --- |
| PySide application/windows/dialogs | [PySide backend](pyside/README.md) |
| File browsing, discovery and indexed search | [File browser](file_browser/README.md) |
| Plain-text editing, syntax and diff views | [Code editor](code_editor/README.md) |
| Markdown reading/editing | [Markdown](markdown/README.md) |
| Archive entry lists and previews | [Archive contents](archive_view/README.md) |
| Other widgets, workspaces, notifications and reader chrome | [UI API reference](REFERENCE.md) |

File browsers and documents use `Workspace` for tab ordering, splitting, dragging
and normal native detached windows. Views own cooperative `prepare_close`/`idle`
contracts. `document_host` embeds retained readers/editors when an application
registers a host, and otherwise opens standalone windows.

`Workspace(..., policy=WorkspacePolicy(...))` opts into multi-tab detached
containers. Single-header visibility is independent of last-tab movement policy.
`new_view(workspace)` binds creation to the requesting container; ordinary
factories still receive their original argument. Views can expose a
`workspace_controls` layout for local controls when their header is hidden.
`setup_container(workspace)` installs application-specific footer/controllers in
new detached containers. `adopt` transfers the existing dock, checks compatibility,
and rolls back layout/ownership if the destination fails. Closing a detached
container restores its tabs to its main workspace without closing the views.
Constructors without a policy retain the existing native floating-dock behavior.

Detached title bars support returning the whole container through drag-and-drop
or their context menu. `drop_reveal` on the main workspace can temporarily reveal
its destination and return a callback that restores the previous view on an
abandoned drag. The last detached tab can always return home; the last main tab
still follows `allow_last_tab_detach`. Hidden tab headers have zero height.
`WorkspacePolicy(max_tabs=1)` rejects both creation and incoming transfers beyond
one tab; `allow_new_tabs=False` removes the creation controls and shortcut.

`show_document(window, detached=True, allow_new_tabs=False)` opens an isolated
single-document container when a host is registered. `open_markdown` accepts the
same fields. These containers close their document through its normal close
handler, including unsaved-change vetoes. Ordinary detached containers still
return their tabs when the window closes. On macOS the active document's menus
are presented in the native top-level window's system menu bar.

`settings_sections.ScopedSettings` groups retained panels into Application Settings
and Personal. `SettingsSection` identifies scope and section; a lone custom panel
appears directly, while `nested=True` keeps an INI files section visible even when
it is the only section. Removing/restoring sections preserves widgets, selections
and unsaved editor buffers. Storage policy and writes stay with the application.

Generic `outline` and `entry_views` widgets keep domain identities opaque.
`notifications` owns result history and presentation; workers stay in their
feature or document. See the API reference for these contracts.

[Library overview](../README.md)
