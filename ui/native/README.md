# Native Toga components

This optional package supplies Toga navigation and native image gestures.
Importing `commonUtils.ui.native` or `navigation_state` loads no toolkit.
Import `navigation`, `routes` or `image_canvas` explicitly in a Toga host.
The consumer selects and installs its Toga backend and owns application workflows.

The namespace also preserves the existing desktop `display_msg_box_ok` and
`display_msg_box_ok_cancel` APIs. They load the desktop dialog backend only when
called; importing the native navigation package does not load a UI toolkit.

## Configurable navigation

`NativeNavigationHost(items, state=None, on_select=None, prefer_sidebar=True)`
accepts one to five `(identity, label, Apple symbol, Android drawable name)` tuples.
Identities must be unique. Android's `home` icon name selects the vector house;
other names resolve through `android.R.drawable`. The optional state must have
the same destinations in the same order. Labels and destinations are caller data.

`install(window)` establishes native containment and layout/keyboard listeners;
`uninstall()` restores them, and `dispose()` retires the host's widgets and
callbacks. `activate(identity)` selects a destination without rebuilding views.
`Routes(host, guard, changed, intent=None)` retains a separate stack per destination.
The guard controls navigation, and the consumer decides document-close behavior.
Install/uninstall routes with their host to register/remove native Back delegates.

`host.chrome.set_hidden(hidden, navigation=None)` hides native bars and restores
their previous visibility. A consumer with a custom split/detail controller can
supply that navigation controller explicitly. Screen changes must reconcile
visibility. On Android, hidden mode also hides system status/navigation bars with
`WindowInsetsControllerCompat` and allows temporary edge-swipe revelation. It
snapshots each bar's original visibility and system-bar behavior once per hidden
context and restores them on exit. Insets are reapplied so host content can use
the newly available viewport. `chrome.restore()` runs during host uninstallation.
The Android adapter retains LinearLayout's weighted/MATCH_PARENT content sizing
after each Toga refresh; measured child sizes must not freeze the viewport during
rail, system-bar or window-size transitions.

`host.chrome.set_page_swipes(active, navigation=None)` reserves horizontal reader
gestures by disabling the Apple navigation controller's edge and, when available,
content-pop recognizers. Hosts reconcile it on screen changes independently of
bar visibility. Leaving the reader, changing controllers or uninstalling restores
the recognizers' original enabled states; explicit Back buttons remain available.

## Native image canvas

`ImageCanvas(image=None, on_page=None, on_toggle=None, page_swipes_at_edges=False, magnifier_enabled=False, description=..., **kwargs)`
extends Toga ImageView. It fits and centers an image, bounds zoom to 1–6, allows
pan while zoomed, and emits left/right paging callbacks at fit scale. It does not
load files, determine page order, decrypt content or save positions. Supply a
description appropriate to the consumer's content.
Set `page_swipes_at_edges=True` to accept Apple paging swipes within the outer
24 points too. The host must also reserve paging through `chrome.set_page_swipes`
to prevent navigation pop gestures from competing; tap edge filtering is retained.

Set `magnifier_enabled=True` to opt into the iOS/Android hold lens (off by
default). Hold 400 ms, drag to move the 2× lens, release to dismiss. The lens
magnifies the image beneath its own center, using decoded pixels in memory,
and suppresses tap/paging while active. Its 180×140 logical-unit size scales
with the viewport’s shorter side, up to 360×280 on tablets. The lens stays
inside the viewport; continued dragging toward an edge moves the sample toward
the viewport border independently of the lens frame, including the bottom edge.
Its frame is lowered by 4.5% of the viewport height from the original
36-unit above-finger gap, allowing overlap with the finger. It clamps at the edges. Image margins remain blank rather than snapping to the image edge.
A second finger cancels it. Disabling the property, replacing the image, resizing,
detaching or disposing clears the overlay and pending hold. Hosts own eligibility
such as fullscreen-only use; the canvas has no comic or fullscreen policy.

Use `set_zoom(value)` and `fit_page()` for commands. `dispose()` clears image,
callbacks and native gesture ownership before a page is permanently retired.
Setting `image=None` alone supports temporary suspension and later reuse.

## Consumer packaging

The Android host must compile the Java sources under this package's `android/`
directory, including `ImageCanvasView` and `NavigationBack` in
`io.github.ispaure.commonutils`. These require the AndroidX/Material dependencies
provided by the validated Toga Android host. Include that directory in the
generated Gradle Java source set; copying Python alone is insufficient.

`tools.mobile_ci.stage` includes native Python/Java sources. Local untracked native
sources require `allow_dirty=True` and mark the manifest dirty. Release staging
requires committed sources. Consumers must include Java bytes in their source
fingerprint and propagate the dirty flag into release validation.

Current adapters were developed against Toga 0.5.7. Backend internals and native
lifecycles require validation when upgrading; this is not a promise of compatibility
with every Toga version. Host tests cover consumer independence and portable
imports; real iOS/Android checks cover containment, gestures, Back and layout.

[Shared UI guide](../README.md)

## Cooperative event loops

`event_loop.bind_cooperative_loop(loop)` restores the owned running-loop context
around Toga 0.5.7 Android cooperative dispatch, then restores the native caller's
context. Repeated binding is idempotent; loops without `run_delayed_tasks` are
unchanged. This imports asyncio only, without selecting a UI backend.

## Memory and configuration notifications

`memory.MemoryPressure(app, on_pressure=..., on_configuration=None)` subscribes
to iOS memory warnings and Android component callbacks. Delivery uses the app's
asyncio loop; bound callbacks are weakly held. `dispose()` unregisters listeners
and suppresses already queued notifications. The host owns active-window guards,
resource release and theme updates. Unsupported backends install no native hooks.

## System documents

`documents.pick_document(app, title=...)` returns `(access, reference)` or None
on cancellation. `runtime.document_access` supplies scoped iOS NSURL, Android
ContentResolver and local-path stream adapters. Access closes with the context;
no persistent grants or bookmarks are retained. Import into host-owned storage
while that context is open.

`documents.export_stream(app, name, open_source, mime_type=...)` selects a system
destination and streams from a context-manager factory. Names must be single file
names. The host supplies MIME type, limits and content policy. Android output
closes on failure; iOS stages in app data and removes staging after picker completion
or cancellation. Local exports stage before replacement and retain the old file on
copy failure. Native providers determine their own publication guarantees.

## Menus and presentation

`menus.NativeMenu(button, actions, invoke=..., context=..., fallback=...)` builds
Apple primary-action menus or Android anchored popups. Actions are `(title, callback)`
pairs; `invoke(callback)` performs host guards/scheduling. `context()` supplies the
Android activity and `fallback()` supplies other-backend UI. `dispose()` detaches
native callbacks and rejects stale actions. Hosts retain the menu with its view.

`presentation` supplies `surface`, `list_button`, `template_icon` and
`scroll_content`: optional native colour/tint/row behavior and fresh scroll parenting
for the pinned Toga layout engine. They do not choose destinations or document policy.

## Native text search

`editor_search.EditorSearch(editor, container, insertion_index=1)` supplies literal
Find/Replace, case matching, wrapping and native UTF-16 selection for a Toga text
input. `toggle()` inserts/removes its panel. Call `changed()` when editor text
changes to invalidate the retained match. The host owns drafts, session guards,
read-only policy and saving. No Qt search widget is imported.

## Markdown documentation wiki

Explicitly import `ui.native.markdown.MarkdownWikiView` in a Toga host. It takes
`directory` (Directory or path), optional initial `path`, `width=390`,
`font_size=16` and optional `render(text, font_size, local_links=True) -> HTML`.
Place its `view` widget in your host and call `reflow(width)` on resize.
The default inert renderer, `ui.native.markdown_preview`, requires the pure-Python
`markdown-it-py` package (Logistics pins 4.2.0 in its mobile manifest). It renders
CommonMark plus tables and strikethrough, including nested lists, quotes, emphasis,
reference links and heading IDs. HTML is escaped, image alt text is displayed,
and external links remain inert. Tables/code scroll horizontally without widening
the page. Input/output limits remain 1/2 MiB, without scripts or remote resources. A host renderer may inject its
own CSS palette. Neither module imports Qt or a consumer application.

The read-only view owns its nested folder controls, inline file/title or source
text search, page selection and relative Markdown links. A hamburger toggles the tree in narrow allocations; when the tree and article
fit together it pins the tree beside the article. Browse state
survives page changes and resizing. Links open only cataloged local pages. Hosts own routing,
close behavior and document editing. Directory/title/search rules come from
`formats.markdown_wiki.MarkdownWiki`, shared with the Qt Markdown viewer. Import
the Qt or native entry point explicitly for the host toolkit; importing one does
not require installing the other toolkit.

The wiki top bar exposes Back/Forward history and Up via `back()`, `forward()` and
`up()` (success booleans). Only successful page opens enter history; opening a new
page after Back drops forward history. Failed history loads retain the current
position. `MarkdownWiki.parent_page(path)` supplies shared Up semantics: an article
opens its containing folder's landing page, a landing page opens its parent's,
and the root accepts README/index fallbacks. Missing parents disable Up.

## Adaptive sidebar and detail

`ui.native.adaptive.AdaptiveSidebar(sidebar, detail, width=..., policy=...)` mounts
retained widgets in its `view`. Put its accessible `menu_button` in a toolbar;
`toggle()`, `show_sidebar()` and `show_detail()` switch compact views. Hosts call
`reflow(usable_width)` after native layout/resize. `expanded` reports whether both
panes fit. Widgets, queries and application state are never recreated by reflow.

`SidebarPolicy` uses a sidebar width, minimum detail width and gap (260 + 448 + 12
by default). These are logical units: iOS points or Android dp, after safe areas,
rails and app-specific margins. `allocated_width(widget, fallback)` measures the
parent's native allocation, converts Android pixels by display density, and caps
it at the host's current window/pane width. Use this instead of physical screen
resolution, device names or a tablet flag. `SidebarPolicy` and measurement can be
imported without Toga or Qt; constructing a pair explicitly loads Toga.

The Markdown wiki subtracts its own 24-point horizontal margins and hides the
hamburger while its tree is pinned. Its host supplies the current destination's
content allocation, so split-screen, resizable iPad windows and foldables follow
the same fit rule. No iPhone Duo, iPad or Android model exception is needed.

`presentation.navigation_button(direction, label, on_press=..., enabled=...)`
supplies shared Back/Forward/Up controls with UIKit symbols, Android vectors,
accessible action labels and 48-point/dp touch targets. The wiki uses these arrows
alongside the hamburger; disabled history and parent actions remain disabled.

Relative page links resolve from the current source file, including `../`.
An extensionless destination tries `.md` and `.markdown`; a directory tries its
same-named page, README, then index. Linked Markdown may be outside the tree and
still participates in page history. Explicit local text/code links open the host
text editor separately and never enter wiki history; missing and binary files
report an inline error. Files are never executed.

Native hosts provide `MarkdownWikiView(..., open_file=callback)` for non-Markdown
text links. The callback receives the resolved Path and owns editor/session
presentation. Rendered hrefs encode the source-relative destination under the
current render URL so WebView URL normalization cannot discard parent segments.
Stale render URLs remain ignored. The view does not open arbitrary URL schemes.

Both `[test.md|Test]` (alias form) and `[Test](test.md)` (standard Markdown) show
Test and open test.md. The double-bracket `[[test.md|Test]]` form also works.
Alias-like text inside inline code or fenced code stays literal.

Tree rows reserve a 48-unit disclosure column for both pages and folders and
indent every child level by 20 logical units. Heading links scroll through a
host-evaluated, data-serialized DOM lookup, including fragments on linked pages;
this avoids Android WebView ignoring the HTML base URL. Document scripts remain
blocked by the content policy. `open_page(..., fragment="heading-id")` requests a
scroll after the page loads.

## Wiki scopes and landing pages

A conventional wiki has a `docs/docs.md` scope landing, audience subfolders and
same-named nested pages such as `banana/banana.md`. Start pages with an H1 after
optional YAML properties; the heading supplies the visible title. Parent pages
should link to their children so the hierarchy also works outside the viewer.

Explicit Markdown links into another wiki replace the sidebar catalog with that
wiki's scope. Back and Forward restore the destination's scope as well. Search
clears when changing scopes so a previous query cannot hide the new guide.
`formats.markdown_wiki.documentation_root(path, fallback)` resolves conventional
scopes without application-specific ownership rules. Custom directories retain
the supplied root while browsing contained pages. This is navigation scoping,
not an access boundary; normal local-file access checks still apply.
