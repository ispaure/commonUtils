# Extension points

Extend the data layer for new file meanings, and install UI capabilities separately.
Declarations do not discover plugins or execute initialization by themselves.

## Register a project file type

A registered class must derive from File and accept a path. Keep construction and
detection cheap: they can run during listings. Defer content reads to explicit
methods or browser panel loaders. This self-contained example removes its rule
when finished, which is useful in tests:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.filesystem.files import File
from commonUtils.formats.registry import file_from_path, file_types, register_file_type

class ProjectFile(File):
    pass

registration = register_file_type(ProjectFile, ('project',), priority=10,
                                  owner='example_project')
try:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'example.PROJECT'
        path.touch()
        assert isinstance(file_from_path(path), ProjectFile)
finally:
    file_types.unregister(registration)
```

Rules accept dotted/bare and compound suffixes; matching is case-insensitive.
If both extensions and a detector are supplied, **both must match**. A detector
receives Path and its exceptions propagate. Higher priority wins; newest wins an
equal-priority tie. Unknown types become File. Invalid classes/rules raise
TypeError or ValueError. Register before the first listing; existing Directory
instances see later rules, but already-created File instances keep their class.

Use `FileTypeRegistry()` for an isolated resolver; it does not automatically seed
built-ins. The module-level helpers use the shared registry. Keep registration
handles for `unregister`; owner scopes and `set_owner_enabled(owner, enabled)`
allow toggling without losing rule order. Revision changes let browser models
invalidate resolved types. This is not a disk-based plugin installation system.

## Replace one existing type

Use `override_file_type(Base, Subclass, priority=...)` or
`Feature.file_type_overrides`, not a broad extension rule, when augmenting a built-in.
The replacement must be a strict subclass. Only an **exact resolved class** is
replaced; replacing TXTFile does not erase CSV/Markdown specialization. Chains of
subclass replacements are supported. Direct constructors and old instances are
unchanged. See the [complete override example](../reference/formats/formats.md#replace-an-existing-type-with-your-subclass).

## Declare browser behavior

A `Feature` groups owned `FileType`/`FileTypeOverride` declarations with a
`BrowserExtension`. The [runnable guide](../reference/ui/features/features.md) includes a
full window plus realistic panel/action/activation examples.

The host retains the declaration, calls `register_types()` before listing and
`install_browser(browser, host=window)` for each browser. Registration is idempotent;
installation returns the existing binding when repeated with the same declaration
and browser. Installing a different explicit controller there raises ValueError.

| Extension | Implementer contract |
| --- | --- |
| `SelectionAction` | Unique id within feature, label, accepted classes and `handler(context)`; GUI thread, accepted selection only |
| `is_available(context)` | Cheap per-item predicate during menu building; handler revalidates current state before work |
| `FileActivation` | First matching activation handles a file; folders still navigate; feature activation precedes the file hook |
| `folder_fields(directory, stats)` | Return field pairs from shared FolderStats; do not initiate another recursive scan |
| `create_controller(host)` | Own per-browser state/jobs; optional `prepare_close()` and `idle` for safe shutdown |
| `Feature.initialize` / requirements | Host calls initialization and interprets dependency metadata; no automatic ordering is promised |

`ActionContext.selection` contains accepted objects in captured order; `paths`
returns their Paths. `item`/`path` require exactly one item or raise ValueError.
`browser`, `host` and `controller` give the binding context. Mixed unsupported
items are filtered out, not recursively expanded. Shared commands can use
`shared_key`; participating declarations must agree on accepted types and routing.

`feature.set_enabled(False)` disables owned formats and all live bindings.
`binding.set_enabled(False)` affects only one browser layer. `binding.remove()`
permanently detaches that layer and rejects stale menu actions. None of these
cancels existing jobs or reverses initialization. The host retains controllers
until they finish. See [shutdown](architecture.md#initialization-and-shutdown).

Class references can be deferred as `package.module:Class` strings. Resolution
happens when registration/binding needs the class, so discovery can inspect
requirements without importing optional dependencies. Check dependencies first.

## Supply metadata and thumbnails

Override `FilesystemObject.browser_panels()` with BrowserPanel declarations whose
load callback returns BrowserDetails. For example:

```python
from commonUtils.filesystem import BrowserPanel, BrowserDetails
from commonUtils.filesystem.files import File

class ReportFile(File):
    def browser_panels(self):
        return (BrowserPanel('report.summary', 'Report', self.load_summary),)

    def load_summary(self):
        return BrowserDetails(fields=(('Report', self.file_name),),
                              message='Project metadata can be loaded here.')
```

Panel loading runs on workers. Do not construct widgets there. Return field pairs,
message, thumbnail bytes and optional payload. Generic filesystem information
remains available. Set `browser_has_thumbnail=True` and implement
`browser_thumbnail(size)` for encoded image bytes bounded by the supplied
physical-pixel size; return an empty result when unavailable. Keep editing in
separate actions and refresh affected paths afterward.

The older `browser_actions`, `browser_activate`, service/action providers and
`install_extension` are lower-level APIs. New grouped features should use
Feature declarations to keep ownership coherent.

## Other reusable customization boundaries

- A Workspace factory returns a QWidget and may expose title, close and idle
  protocols. `dock_group` restricts compatible transfers; `WorkspacePolicy` opts
  into richer detached-window behavior. See [workspace contracts](../reference/ui/workspaces.md).
- INI typed keys are an opt-in convention. Subclass INISettingsEditor for extra
  validation before saving; applications own domain rules and post-save reload.
  See [configuration](../reference/configuration/configuration.md).
- ArchiveContents accepts entries/previews and emits requests. Supply workers and
  credential/error policy in the host; see [archive integration](../reference/archives/archives.md).
- Code diff/merge Apply callbacks change host-owned buffers. The host owns stale
  checks, undo, offset conversion and persistence; see [code editing](../reference/ui/code_editor/code_editor.md).

[Developer hub](developer.md)

File types can supply `browser_thumbnail_badge()` for a short live thumbnail
label. This is a GUI-thread painting hook: do not parse archives, block or open
dialogs. Seed expensive summary metadata from `browser_thumbnail(size)` on its
worker and read only bounded local state while painting. Empty strings omit the
badge. FileViews owns periodic repainting and stops it during browser shutdown.
