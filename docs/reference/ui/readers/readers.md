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

[Shared reader workflows](../../../user/components/components.md) and [Markdown](../markdown/markdown.md).

## Speech presentation and highlights

`ReadAloud` uses a percent slider (50–200%, 25% detents), a sleep timer with an
icon reset and bold countdown, and backward/play/forward/stop controls. Timer
elapsed time follows a monotonic deadline and freezes in paused/stopped states.
`positionChanged(-1, -1)` retires speech-owned highlights before skip requeue so
consumers can clear mirrored panes. The next word emits its replacement range.
Search and other untagged extra selections survive cleanup. See the
[read-aloud workflow](../../../user/markdown/markdown.md#read-aloud).

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
