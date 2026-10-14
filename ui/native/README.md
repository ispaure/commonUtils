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
visibility. `chrome.restore()` runs during host uninstallation.

## Native image canvas

`ImageCanvas(image=None, on_page=None, on_toggle=None, description=..., **kwargs)`
extends Toga ImageView. It fits and centers an image, bounds zoom to 1–6, allows
pan while zoomed, and emits left/right paging callbacks at fit scale. It does not
load files, determine page order, decrypt content or save positions. Supply a
description appropriate to the consumer's content.

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
