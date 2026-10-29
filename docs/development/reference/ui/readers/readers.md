# Shared reader controls

Reader menus, fullscreen controls, read-aloud presentation and wheel navigation shared by document readers.

Import implementations from `commonUtils.ui.readers.<module>`.
Import widgets and helpers directly from these modules. Package imports do not
eagerly load their widgets. Former flat `commonUtils.ui.<module>` forwarding
modules have been removed; update imports and mock patch targets to this package.

## Modules

- `reader_chrome`
- `reader_menus`
- `read_aloud`
- `page_wheel`
- `layout` (portable control geometry; no Qt/native imports)

[Shared reader workflows](../../../../user/components/components.md) and [Markdown](../markdown/markdown.md).

## Reader edges and progress metrics

`layout.READER_LAYOUT` owns the reader touch extent, progress track/thumb sizes,
row spacing, overlay side gap and desktop outer margins. Desktop `reader_chrome`
exports its existing margin/spacing names from this policy. Consumers may use the
portable policy without importing Qt. Native hosts supply logical geometry at
layout time; the library contains no device model tables or inferred radii.

`remaining_clearance(edge, safe_edge, trailing=True)` returns only the unconsumed
part of a safe inset. Applying a system inset and then adding the same inset to
a footer is incorrect. Use one coordinate space, including in split windows.
`rounded_clearance(start, stop, corners, vertical=False)` computes the leading and
trailing safe coordinates for a horizontal row or vertical progress strip. Each
corner is `(trailing_axis, trailing_cross_axis, center_x, center_y, radius)` in the
host's coordinate space. The calculation follows the circular boundary only
where the row intersects it; it does not reserve a full radius along every edge.
`overlay_insets(width, height, safe, corners=(), margin=12, extent=48)` merges
system insets and corner clearance for a bottom overlay. It returns left, top,
right and bottom padding, without changing the underlying media canvas.

UIKit hosts use public safe areas, which already protect screen curvature.
Android hosts can supply `WindowInsets.getRoundedCorner` metadata on API 31+;
missing metadata preserves ordinary bar/cutout insets. Never guess a radius or
use private screen properties. Native acceptance still needs rotation, changing
window bounds, and any supported fold postures; pure geometry tests alone do
not certify a particular device.

## Speech presentation and highlights

`ReadAloud` uses a percent slider (50–200%, 25% detents), a sleep timer with an
icon reset and bold countdown, and backward/play/forward/stop controls. Timer
elapsed time follows a monotonic deadline and freezes in paused/stopped states.
`positionChanged(-1, -1)` retires speech-owned highlights before skip requeue so
consumers can clear mirrored panes. The next word emits its replacement range.
Search and other untagged extra selections survive cleanup. See the
[read-aloud workflow](../../../../user/markdown/markdown.md#read-aloud).

## Portable playback and the Qt adapter

`ReadAloud` delegates playback, pause/resume, speed, skipping, word ranges and
retired-generation rejection to `runtime.speech.SpeechSession`; its listening
budget uses `PlaybackTimer`. `qt_speech.QtScheduler` supplies GUI-owned single-shot
timers and `QtSpeechEngine` translates QTextToSpeech state/word callbacks into
portable session events. Completion schedules the next utterance after the native
state callback returns, avoiding reentrant engine starts.

The adapter checks the installed engine's word-progress and pause/resume
capabilities. Utterances are bounded at 3,000 UTF-16 units with native word events
or 350 without; the portable session supplies approximate progress where needed.
Host selection/UTF-16 mapping, highlighting and voice preferences stay with
`ReadAloud`. A Qt host still needs an installed usable speech engine; portable
session tests do not establish voice availability on a device.

Read-aloud defaults to **Automatic (detect text)**. Each fresh Play detects the
selected passage or text starting at the visible position. The optional
`language_provider` callback supplies a fallback language declaration. Automatic
mode chooses an available locale and reports a missing language voice; explicit
language/voice selections remain manual overrides. The automatic mode disables
the voice selector. Installing `langdetect==1.0.9` enables text detection.
