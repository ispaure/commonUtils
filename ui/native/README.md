# Native Toga components

This optional package supplies Toga navigation and native image gestures.
Importing `commonUtils.ui.native` or `navigation_state` loads no toolkit.
Import `navigation`, `routes` or `image_canvas` explicitly in a Toga host.
The consumer selects and installs its Toga backend and owns application workflows.

The namespace also preserves the existing desktop `display_msg_box_ok` and
`display_msg_box_ok_cancel` APIs. They load the desktop dialog backend only when
called; importing the native navigation package does not load a UI toolkit.

## Recycled lists

`ui.native.recycled_list.RecycledList` extends Toga DetailedList with recycled
UITableView cells on iOS and a Java ListView adapter on Android. Import it
explicitly; Toga remains optional for non-native consumers. The Android host must
compile `ui/native/android` as a Java source root, including
`io.github.ispaure.commonutils.FileListView`.

Rows supply `title`, `subtitle`, `folder` and `icon` (a Toga image or `None`).
For incremental thumbnails, also supply `index` and `thumbnail`; mutate the
current source row to update its visible image without rebuilding the table.
`on_visible(row)` reports rows needing images, `on_select` activates a row, and
`on_primary_action(row=...)` handles contextual actions. `select_index(index)`
changes selection without activation. `clear()` scrubs rows and selection.
Use `primary_action=None` when contextual actions are unavailable.

`ListAppearance` injects `palette(dark)`, `apple_color(role)`, `high_contrast()`
and `icon(folder)` callbacks, plus positive integer native dimensions:
`row_height=48`, `body_text=17`, `caption_text=13`, `icon_size=28`. Text dimensions
configure Android's sp fonts; UIKit retains native text fonts. Palette roles are
`text`, `muted`, `surface`, `hover`, `accent` and `border`; Apple also accepts
`transparent`. Defaults use neutral Android colors and semantic UIKit colors.
Hosts call `refresh_palette()` for Android theme/high-contrast changes; Apple
color callbacks should return dynamic colors. No app-wide theme registry is
installed by the shared component.

`thumbnail_image(image, size=28)` fits a row image while preserving the UIKit
renderer scale on Retina devices. Generic browsing composition and its lifecycle
are described in the [native browser guide](../native_browser/README.md).

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
On iOS, a software keyboard in the owning key window temporarily hides destination
tabs and restores their previous visibility on dismissal or host uninstallation.
UIKit's tab-bar visibility API releases the tab bar's safe-area reservation on
iOS 18 and later; older systems use native view visibility. Floating keyboards
hide the tabs without claiming a full-width keyboard inset. Immersive reader
chrome keeps independent restoration ownership; leaving a reader while typing
reapplies temporary keyboard suppression.
`tabs_hidden()` reports the active UIKit tab-container visibility, which can differ
from `tabBar.isHidden`. Keyboard geometry changes coalesce a consumer resize
callback even when the window dimensions stay constant, so callers can release
floating-bar clearance and reflow their content.
Android bottom-bar/rail transitions suppress Toga's programmatic selection event;
rotation changes presentation without invoking host navigation or retiring routes.

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
The Android adapter disables Material 1.12's automatic bottom-navigation inset
listener: the window/host already reserves system and keyboard space. Otherwise
Material adds the IME height as bar padding during `adjustResize`, expanding the
bar until the weighted content has no height. Destination buttons retain their
normal height above the keyboard. When the IME leaves less than 400 logical units
of visible window height, the adapter temporarily hides application navigation
and the title bar until dismissal. It latches this state through layout changes
and rail transitions, restores original visibility, and yields to immersive
reader chrome ownership. System bars remain under their existing owner.
The adapter also removes Toga's 100-unit root height floor while installed, so
very short IME viewports use the actual window allocation instead of overflowing.

`host.chrome.set_page_swipes(active, navigation=None)` reserves horizontal reader
gestures by disabling the Apple navigation controller's edge and, when available,
content-pop recognizers. Hosts reconcile it on screen changes independently of
bar visibility. Leaving the reader, changing controllers or uninstalling restores
the recognizers' original enabled states; explicit Back buttons remain available.

## Native image canvas

`ImageCanvas(image=None, on_page=None, on_toggle=None, page_swipes_at_edges=False, magnifier_enabled=False, magnifier_zoom=190, on_magnifier_zoom=None, page_axis='horizontal', description=..., **kwargs)`
extends Toga ImageView. It fits and centers an image, bounds zoom to 1–6, allows
pan while zoomed, and emits left/right paging callbacks at fit scale. It does not
load files, determine page order, decrypt content or save positions. Supply a
description appropriate to the consumer's content. Set `page_axis='vertical'`
at construction for up/down paging (up emits +1, down emits -1); the default
horizontal axis retains left/right paging. Both axes retain tap, pinch/pan and
hold-lens arbitration, and page swipes require fit scale.
Set `page_swipes_at_edges=True` to accept Apple paging swipes within the outer
24 points too. The host must also reserve paging through `chrome.set_page_swipes`
to prevent navigation pop gestures from competing; tap edge filtering is retained.

Set `magnifier_enabled=True` to opt into the iOS/Android hold lens (off by
default). Hold 400 ms, drag to move the lens, release to dismiss. The lens
magnifies the image beneath its own center, using decoded pixels in memory,
and suppresses tap/paging while active. Its 180×140 logical-unit size scales
with the viewport’s shorter side, up to 360×280 on tablets. The lens stays
inside the viewport; continued dragging toward an edge moves the sample toward
the viewport border independently of the lens frame, including the bottom edge.
Its frame is lowered by 4.5% of the viewport height from the original
36-unit above-finger gap, allowing overlap with the finger. It clamps at the edges. Image margins remain blank rather than snapping to the image edge.
Keep the original finger holding the image and tap the 33-unit −/+ buttons
with another finger to change `magnifier_zoom` through 150, 170, 190, 210, 230 and
250 percent (default 190). The controls sit at the bottom left/right corners,
6 units outward and 9 below the lens, clamped to the viewport. No percentage
label overlays the image.
UIKit adds the buttons as siblings of the clipped lens; Android uses a split-touch
popup at the lens's bottom edge. The original hold stays on the image; button taps do not
page or toggle controls. Releasing the original hold dismisses the lens and buttons.
`on_magnifier_zoom(canvas, percent)` receives a requested change before applying it;
return `False` to reject a failed host save. Assigning `magnifier_zoom` updates a
visible lens without firing the callback. `change_magnifier_zoom(direction)` steps
once and `request_magnifier_zoom(percent)` requests an explicit supported level.
The host owns persistence and synchronization across canvases. A second finger
away from the buttons still cancels the lens for ordinary image pinch zoom. Disabling the property, replacing the image, resizing,
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
on cancellation. `runtime.resources.documents` supplies scoped iOS NSURL, Android
ContentResolver and local-path stream adapters. Access closes with the context;
no persistent grants or bookmarks are retained. Import into host-owned storage
while that context is open.

`documents.export_stream(app, name, open_source, mime_type=...)` selects a system
destination and streams from a context-manager factory. Names must be single file
names. The host supplies MIME type, limits and content policy. Android output
closes on failure; iOS stages in app data and removes staging after picker completion
or cancellation. Local exports stage before replacement and retain the old file on
copy failure. Local destinations respect the host's registered provider boundaries
before source access and again before publication; denied exports remove their
own staging file. Native providers determine their own publication guarantees.

## Menus and presentation

`menus.NativeMenu(button, actions, invoke=..., context=..., fallback=...)` builds
Apple primary-action menus or Android anchored popups. Actions are `(title, callback)`
pairs; `invoke(callback)` performs host guards/scheduling. `context()` supplies the
Android activity and `fallback()` supplies other-backend UI. `dispose()` detaches
native callbacks and rejects stale actions. Hosts retain the menu with its view.
Deferred recycled-row menus retain the copied Objective-C completion owner across
asynchronous command loading; a Rubicon `ObjCBlock` alone retains only its pointer.
Recycled rows may carry `hidden=True` to mute their title on iOS and Android.
Every cell bind restores the current row's colour, including after recycling;
Android selected rows retain the palette's selection foreground for contrast.

`presentation` supplies `surface`, `list_button`, `template_icon` and
`scroll_content`: optional native colour/tint/row behavior and fresh scroll parenting
for the pinned Toga layout engine. They do not choose destinations or document policy.

`hierarchy_row(label, depth=0, expanded=None, on_toggle=None, on_activate=None,
selected=False)` provides distinct 48-unit disclosure/title targets, reserving
matching columns for leaves. `HierarchyList(entries, choose, row_style=None,
selected=None)` consumes preorder entries with `label` and `depth`, owns collapsed
rows, and passes the original entry to `choose`. `selected(entry)` identifies the
current destination; `row_style(row, selected)` lets hosts apply their palette.
Rows expose `disclosure` and `title_button`; no filesystem or navigation policy
is embedded. The Markdown wiki uses the same row builder for folder/page actions.

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
`formats.markdown.wiki.MarkdownWiki`, shared with the Qt Markdown viewer. Import
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

## Rendered Markdown search

`markdown_search.MarkdownPageSearch(web, container, insertion_index=0, valid=...)`
owns a transient two-row page search panel. `show()`/`hide()` insert/remove it;
`set_library_query(text)` supplies independent library marks. Call `loading()`
before replacing HTML and `loaded(reveal=True)` from the WebView load callback.
For explicit heading navigation use `reveal=False`, then scroll to the heading.
Preserve other load callbacks, including host font bindings. The validity callback
gates asynchronous evaluation/results; call `dispose()` before retiring private
content or an owner to clear queries, pending debounce and visible controls.

Search runs only through host-evaluated, JSON-serialized JavaScript. Authored
scripts remain blocked. Text ranges cover literal, case-insensitive matches across
inline elements, with block boundaries kept separate. Each scope retains at most
5,000 ranges. Modern WebViews use CSS highlight ranges; older engines paint empty,
pointer-transparent overlays that follow scroll/resize without splitting text
nodes. Both paths retain source DOM, links, user selection and speech marks.
Library queries can match raw Markdown/filenames that have no visible-page match.

`MarkdownWikiView.page_search` exposes this controller. Its navigation button
opens the article before showing search on a phone; hosts using a native toolbar
can expose `show_page_search` in their reader action menu instead.

## Wiki scopes and landing pages

A conventional wiki has a `docs/docs.md` scope landing, audience subfolders and
same-named nested pages such as `banana/banana.md`. Start pages with an H1 after
optional YAML properties; the heading supplies the visible title. Parent pages
should link to their children so the hierarchy also works outside the viewer.

Explicit Markdown links into another wiki replace the sidebar catalog with that
wiki's scope. Back and Forward restore the destination's scope as well. Search
clears when changing scopes so a previous query cannot hide the new guide.
`formats.markdown.wiki.documentation_root(path, fallback)` resolves conventional
scopes without application-specific ownership rules. Custom directories retain
the supplied root while browsing contained pages. This is navigation scoping,
not an access boundary; normal local-file access checks still apply.

## Native source editor

`code_input.CodeInput(loop=..., filename='', on_change=..., highlighting=True, **kwargs)`
extends Toga's MultilineTextInput. It retains the native keyboard, IME, undo and
selection. iOS draws a gutter over UITextView's text canvas; Android attaches
`CodeEditorSupport` to the existing EditText. Logical line numbers follow native
wrapped-line geometry and scrolling rather than estimating character widths.
On Android the input can shrink to 48 logical units instead of Toga's 100-unit
minimum, keeping a writing line and native padding inside short panes. Android disables fullscreen
IME extraction; Source mode keeps the application's toolbar and native editor.
Call `set_filename` on rename, `set_language(alias)` for an override (None restores
detection), and `dispose()` when retiring a view. Existing `.value`, `.readonly`
and EditorSearch contracts remain available; `backend_name` identifies the host
backend for native UTF-16 selection adapters.

Hosts supply Pygments (Logistics pins 2.19.2). Language choices, filename detection
and the Blade grammar are shared with desktop under `formats.code_syntax` and
`formats.code_blade`. `formats.code_spans` produces colour spans and logical-line
starts in UTF-16 coordinates without importing Qt. Colouring runs after a typing
pause on a worker; changed text, language, filename or closed controls reject stale
results. Active IME composition defers recolouring. Native attributes/spans are
changed in place without replacing source text or its selection. Highlighting
falls back to plain text above 128 Ki characters or 20,000 coloured spans; line
numbers and editing remain available. The consumer owns save, private-memory,
restoration and Markdown preview policy. Compile CodeEditorSupport.java with the
other native bridge files on Android.

The Markdown tree scroll content uses the allocated sidebar width (260 logical
units when pinned, the available browse width on phones). This prevents iOS from
retaining the hidden tree's minimum intrinsic width when switching from article
to browse mode. Native documentation probes check the actual title-button frame.

Opening a page expands its ancestor folders, including after scope changes and
history navigation, so the current article is visible in the tree.

## Password entry

Import `PasswordInput` explicitly from `commonUtils.ui.native.password_input` in
an iOS or Android Toga host. Construct it with `placeholder`, `on_confirm` and
optional `style`. It supplies a native password field plus a 48-point eye button,
with accessible Show password / Hide password names and system-colour icons.
The row is at least 48 points tall. `value`, `enabled`, `focus()` and assignable
`on_confirm` delegate to the input; disabling also disables the eye button.
`field` exposes the underlying Toga input and `eye` exposes the reveal button.

`revealed` reports visibility; `set_revealed(bool)` changes it and
`toggle_visibility()` toggles it. Input starts hidden, toggling preserves its value
and selection, and clearing through `value` or the input masks it again.
Only the iOS/Android adapters change native masking; the dummy backend exercises
state and callbacks. No Qt or consuming application modules are imported. Hosts
own persistence, credential validation, background privacy and disposal policy.

## Host-supplied Markdown images

`markdown_body` and `markdown_preview` accept optional `image_source(target)`.
The callback returns `(mime_type, bytes)` or `None`; it owns path resolution,
permissions, revision checks and I/O. The renderer never fetches images itself.
PNG, JPEG, WebP and GIF up to 8 MiB are embedded as data URIs; `OSError`/`ValueError`
and unsupported data fall back to escaped alt text. Hosts must validate raster
content and bound their total I/O. An opted-in preview allows only `data:` image
sources and has a 24 MiB output limit; the default inert preview keeps its 2 MiB
limit and alt-text-only images. Image markup is bounded to 22 MiB per body.

With an image source, `![[relative/image.webp]]` is parsed as an image embed.
The reusable `embedded_image` and `wiki_image` helpers allow formatted editors to
apply the same image policy without loading an application module. Wiki parsing
is opt-in; code spans, fenced code and escaped embeds remain literal.

The default `MarkdownWikiView` renderer uses
`markdown_images.local_image_source(document, root)` for page-relative local
images within the documentation root. A custom `render` callback keeps its old
arguments unless `image_source_factory(document, root)` is explicitly supplied;
then the renderer also receives the per-page `image_source` keyword. Logistics'
Documentation reader opts in through this factory as well.

`markdown_images.folder_image_source(provider, document)` supplies the bounded
shared resolver for folder-backed native readers/editors. It accepts a rooted
provider with `relative`, `entry` and `open` methods; paths resolve relative to
the document's provider key. All reads stay behind that provider, with revision
and access rechecks (including cached resources), no plaintext image files, an
8 MiB/16 megapixel per-image limit and a 16 MiB per-render byte budget. Encoded
spaces, `#` and percent signs are decoded only in the URL path. Network URLs,
absolute paths, root escapes and linked local files are rejected. PNG/JPEG/WebP
use the existing header probe; GIF uses the complete bounded container probe.
Animated WebP remains unsupported by this resolver.

GIF bytes are embedded unchanged, letting iOS/Android WebViews play all frames
in preview and formatted editing. Native image markup caps widths at its content
container. Obsidian `![[image.gif|400]]`, `![Caption|400](image.gif)` and numeric
Markdown alt labels support pixel widths; `400x200` also supplies a height.
Explicit dimensions scale together when capped; width-only hints preserve the
intrinsic aspect ratio. Invalid hints remain ordinary alt text. Hosts retain
source syntax when serializing edits; animation never writes Markdown or files.

### Search input delay

`event_loop.DebouncedCallback(callback)` coalesces native text edits on the app
event loop and invokes the callback after 400 ms without another edit. `cancel()`
retires a pending callback. Native browser filename search delays both filtering
and recursive scanning; editing cancels the previous scan immediately.

## Offline speech and private WebViews

`speech.NativeSpeech(loop)` selects the installed Toga backend, enumerates usable
offline voices and implements the engine contract in `runtime.speech`. Android
progress delivery uses `android/io/github/ispaure/commonutils/SpeechListener.java`;
include the shared native Java root when building. The listener carries opaque
utterance tokens and ranges, not source text or document names. Disposal detaches
native callbacks and suppresses queued deliveries. System media controls, audio
session/privacy policy and document title publication remain consumer-owned.

`private_webview.PrivateWebView(max_html_bytes=..., **toga_options)` creates a
nonpersistent WKWebView on iOS or a cache-disabled Android WebView. Backend
selection follows Toga's factory. `private_webview_supported()` reports those
supported backends. `set_content` checks encoded UTF-8 bytes before entering Toga;
`clear_private_content()` retires callbacks, clears the live document and disposes
the native view idempotently. Unsupported backends fail closed. Callers choose
HTML byte limits and supply navigation, resource and credential-validity policy.
The component does not sanitize HTML or authorize arbitrary URLs.

Consumer host regressions and mocked native disposal cover these adapters.
Physical speech, WebView storage behavior and platform accessibility still need
native-device validation after a backend upgrade.

## Native draw acknowledgement

`ui.native.draw_ready.wait_for_draw(widget, timeout=.5)` waits for a native draw
acknowledgement and returns a Boolean. `False` means timeout or an unsupported
backend, never proof that pixels appeared. Timeout and cancellation remove the
native listener; queued acknowledgements cannot complete a retired wait. Hosts
must recheck route, document and privacy lifetime after awaiting it.

Android hosts compile `ui/native/android`, including `DrawReady.java`. UIKit uses
a temporary noninteractive view. No file-opening or application state is inspected.

## Keyboard dismissal

`ui.native.keyboard.install(window)` installs an iOS observer gesture and returns
a `KeyboardDismissal` (or `None` on other backends). Retain it for the window and
call `dispose()` when retiring it. Outside taps dismiss without consuming the
original touch; editable text controls and WebViews retain selection behavior.

`SearchDismissal(search_widget)` owns one Android outside-touch listener.
Call `bind(roots)` with explicit Toga subtrees when controls are added; retained
controls are not rebound. Text inputs are excluded. `dispose()` makes installed
callbacks inert without retaining every bound row. These helpers do not decide
which toolbars, status fields or editor controls should collapse for the IME.

## Pinch text sizing

`ui.native.text_size.TextSizeBinding(widget, loop=..., get_size=..., save_size=...,
changed=..., active=..., alive=..., minimum=12, maximum=32, web=False, ...)`
installs native pinch recognition through `install()`. Call `attach_load()` for a
WebView, `apply(size)` for settings changes and `dispose()` when retiring a binding.
Native text and existing WebView DOMs update without replacing document content.

Gestures preview a clamped size, save once on completion and restore the current
size on cancellation. `changed()` lets a host refresh related surfaces; without
it, the binding reapplies `get_size()`. `on_error(error)` handles save failures.
`active()` gates gestures and `alive()` gates all updates, including queued reflow.
`alignment()` returns a supported text alignment; `alignment_variable` names the
CSS custom property. Hosts retain format settings, privacy guards and document
ownership. The shared helper imports no application modules.

## Transitions and sliders

`ui.native.transitions.page_direction(previous, current, right_to_left=False)`
returns the page movement direction. `begin_page_slide(widget, direction,
enabled=True, duration=.22)` captures an outgoing UIKit transition;
`finish_page_slide(...)` animates replacement Android content. Call them around
content replacement. Zero direction or `enabled=False` skips animation; platform
reduced-motion/disabled-animation settings remain authoritative. The host chooses
whether E Ink or other application policy disables effects.

`ui.native.sliders.style_slider(widget, apple_color=None, palette=None,
force_ltr=False)` paints slim tracks and circular thumbs while preserving the
widget's full touch area. Supply semantic UIKit colors and Android palette roles
`accent`/`border`; defaults are neutral native colors. Direction follows the
platform unless explicitly forced. Hosts own value reversal, theme refresh
registration, reader progress and page changes.

## Surface appearance primitives

`ui.native.appearance.SurfacePainter` accepts explicit `palette(dark)`,
`apple_color(role)`, `high_contrast()`, and optional button-preparation and
post-paint callbacks. `paint(impl, SurfaceStyle(...))` applies colors, outline,
radius, content insets, optional glass and accessory tint. `batch()` coalesces
nested offscreen painting to each widget's final style. Registries of application
widgets, bar placement, theme installation and E Ink policy remain with the host.

Android templates and immutable color-state lists are cached, but every returned
drawable has independent mutable state. Replacing a background preserves content
padding. `clear_surface_caches()` supports backend replacement. `accessible_name`
sets native labels without changing visible text. `DynamicAppleColors(palette)`
retains dynamic UIKit role providers and their bridge blocks; hosts supply role
values. Neutral default colors are shared by native lists and sliders.

Portable `ui.appearance.colors` supplies `argb`, `contrast_ratio`, and
`readable_accent`. These helpers and importing the native appearance module do not
load Toga or Qt. The host chooses its palette and required contrast policies.

## Consumer-supplied icons

`icons.IconSpec` describes symbol names, fallback text, paths, circles, arcs,
filled contours and optional centered text. `IconRenderer(icons, tint_android=...)`
applies existing button icons or leading glyphs without replacing callbacks or menus.
`apply(..., preserve_layout=True)` retains layout and enabled state. The optional
Android tint callback owns palette policy; default tint follows native text colors.
`android_drawable` returns a fresh mutable drawable. Only immutable Apple symbol
pixels are cached. Applications own named artwork, accessible labels and policy.

## Native form primitives

`forms.wrap_text` uses an explicit measurement function. `fit_text` preserves
source text and caches measurements, using the native Apple font where available;
its optional `style_button` callback supplies consumer presentation.
`fit_section` accepts a `reserved_width(row)` callback for label/control rows.
`FittedLabel` refits changing status text. `disclosure`, `group_rows(surface=...)`
and `collapsible(..., style_button=..., changed=...)` build presentation without
owning preferences, validation or page routing. Group palette roles are explicit.
Collapsed controls stay alive and retain their values.

## Retained native bars

`bars.apple_bar_group` mounts existing controls in a constrained UIKit group;
`native_control` prepares each control, and the caller retains the returned item.
`apple_bar_separator` creates fixed spacing. `apple_bar_title` centers a truncated
label relative to its window (or explicit `reference`), with an explicit color.
Only action groups in the same row constrain title width. `android_bar` returns
(root, title, status), mounting controls returned by `native_control` and reserving
symmetric title clearance. Hosts retain controls and own routes, privacy, status
messages, fullscreen behavior, release and window/app assignment.

## Desktop-native message boxes

`ui.native` is a regular lazy package. Its `display_msg_box_ok` and
`display_msg_box_ok_cancel` wrappers import `ui.native.dialogs` only when called.
That module owns desktop platform dispatch; explicitly imported Toga adapters
remain separate. No neighboring-file loader, synthetic module or standalone
namespace alias is needed. See [UI backend selection](../README.md#backends-and-diagnostics).
