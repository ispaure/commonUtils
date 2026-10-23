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
- [ ] Add focused state-lifetime and workflow regression coverage.
- [x] Implement explicit indexing state and readable scan phases.
- [ ] Implement explicit Markdown state and component dependencies.
- [ ] Update owner documentation and validate affected consumers.
- [ ] Record final evidence and reassess both areas at 7/10 or higher.

[Developer hub](README.md)
