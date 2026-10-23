# Indexing and Markdown readability work

This is the completion record for the October 23, 2026 maintenance pass.
The starting source is `e2f18fd`. Scores are engineering judgments about the
cost of understanding and changing code, not automated quality measurements.

## Completion criteria

Both areas must reach at least 7/10 for maintainability and readability against
these requirements before this pass is complete:

- Mutable state has a declared owner and a visible lifetime. A new scan or
  document must not depend on attributes left behind by a previous operation.
- A reader can follow the main operation through named phases and explicit
  collaborators rather than reconstructing an inherited shared-state contract.
- Components declare the widgets, data and callbacks they need. Merely moving
  methods into another mixin, adding dynamic forwarding or shortening files does
  not meet the goal.
- Existing public APIs, database formats and user workflows remain compatible.
  Consequential changes have behavior-focused regression coverage.
- Owning guides explain the resulting contracts. Relevant shared and consumer
  checks pass; unavailable native checks are stated explicitly.

## Work sequence

1. Record ownership and preserve baseline behavior with focused tests.
2. Separate index operation state from the cache's long-lived session state.
   Make initial/resumed scan and reconciliation use the same explicit state
   initialization. Clarify generation selection, discovery and publication phases.
3. Give Markdown document synchronization, search and editing operations explicit
   owners. Reduce mixin dependencies while preserving widget/public entry points.
4. Exercise cancellation/resume, invalidation, snapshot publication, Markdown
   source/rich transitions, save conflicts, asynchronous saves, navigation and
   close handling. Validate consumers and exact Blue Hole vendor synchronization.
5. Reassess the implemented source against each criterion. Address remaining
   structural gaps before assigning the final scores.

Each coherent implementation step gets a local commit; nothing is pushed.
Tests use disposable databases, documents and caches. No live index is scanned
or rewritten. Saved schemas, private-document boundaries and file-preservation
rules remain unchanged.

## Progress

- [x] Review the current source and identify implicit state dependencies.
- [x] Add focused state-lifetime and workflow regression coverage.
- [x] Implement explicit indexing state and readable scan phases.
- [x] Implement explicit Markdown state and component dependencies.
- [x] Update owner documentation and validate affected consumers.
- [x] Record final evidence and reassess both areas at 7/10 or higher.

## Implemented boundaries

Indexing commit `e4b7419` removes inheritance between the cache and scan
orchestration. The cache owns session state/readers; each writer attempt owns a
fresh `ScanState`; SQLite owns durable progress. The scan controller names
ancestor reuse, seeding, completed-generation reuse, work preparation, discovery
and publication. Cancellation releases transient state while retaining the
existing durable checkpoint semantics. Reconciliation keeps atomic rollback and
old-reader isolation.

Markdown commit `a3681df` introduces `MarkdownDocumentState`, `FormattedEditing`,
`SearchHighlights` and `TableEditing`. The three composed behavior components
receive explicit widgets/data/callbacks instead of sharing the viewer as their
implicit `self`. Two integration helpers remain for reading/actions/saving.
The widget keeps explicit public entry points and host override hooks; `371dc21`
adds coverage preserving host-defined dirty-state signaling. IDE shared text
documents and Notes private-draft retirement use the declared state owner.

## Validation and reassessment

Completed shared validation: 183 isolated test files, 1,241 tests, zero failed
files. The subsequent dirty-state contract review passed 54 focused shared tests
and three IDE Markdown tests. The full IDE subset passed 63 tests across eight
files; Notes passed six tests. Lint and architecture checks passed.

Two macOS filesystem-watcher checks fail under restricted event delivery and
pass outside the sandbox; the complete shared run uses native event delivery.
Tests use fixture directories/caches. These results do not establish Windows,
Linux, iOS/Android device behavior or a live Blue Hole Blender session.

The complete desktop consumer sweep passed 179 isolated files / 1,685 tests.
Blue Hole passed all 33 consumer tests after exporting committed shared source;
its exact committed-file vendor verification passed. The final documentation-only
completion commit is included in the recorded vendor revision before delivery.

| Area | Maintainability | Readability | Basis for the completed assessment |
| --- | --- | --- | --- |
| Directory indexing | 7/10 | 7/10 | Declared per-attempt state, separate cache/SQLite lifetimes, composed orchestration and named scan phases; cancellation/resume, old readers, priorities and process coordination retain coverage |
| Markdown UI | 7/10 | 7/10 | Declared document baselines, three composed components with explicit dependencies, independently tested rich synchronization, preserved host hooks and migrated IDE/Notes consumers |

These are supported engineering judgments rather than automatic scores. Indexing
still has dense SQL and a substantial storage implementation. Markdown still has
a large widget constructor and two UI-integration helpers. Those costs keep both
areas below 8/10, but the operation state and rich/search/table behaviors can now
be understood and tested without reconstructing the former inheritance contract.
All completion criteria above are met; further structural work is deferred rather
than required to justify the 7/10 assessment.

[Developer hub](developer.md)

## Central documentation wiki follow-up

The shared documentation now has a `docs/docs.md` entry and one sidebar scope.
Sixty-five existing guides (including the former root overview) move into the
root wiki, with API references grouped by source owner and component workflows
in `docs/user/`. Every folder has a same-named landing and every page starts with
an H1. Relative document, source and asset links are rebased; source-local
README/user_docs entry points remain short links for older callers.

All 14 documentation-layout, portable catalog and real offscreen viewer cases
pass. Every local link in all 79 wiki pages resolves. No runtime/Perforce API,
consumer build architecture, dependency or data schema changes. Work is local
only; no remote was pushed.

## Image encoding phase ownership

The optional Pillow encoder now expresses color/alpha conversion, aspect-ratio
resizing and metadata preparation as three private functions in its existing
module. The public function exposes phase order and the caller's allocation
boundary. Its signature, output policy and consumer ownership do not change.

Eight shared contracts pass, including lazy quality timing, pre-allocation ICC
errors, unsupported-encoder stage ownership, nested EXIF dimensions and palette
transparency. A separate old/new comparison across 48 real input/output profiles
confirms identical bytes, errors, allocation events and retained sources. Existing
Logistics image and comic consumer checks pass; no user images are modified.
The initial parity-fixture generator could not serialize a new nested EXIF IFD
into TIFF; PNG retains nested-IFD coverage and TIFF covers CMYK/Lab profiles.
