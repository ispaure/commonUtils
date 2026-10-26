# Documentation audit — October 2026

For the current source review and next changes, use
[Refactoring commonUtils safely](refactoring.md). The dated record below includes
findings that later sections explicitly close; it is not the current backlog.

## Findings and structure

The previous documentation had useful package-local references but no audience-based
entry point. The root README repeated the feature guide's complete browser example;
Layout policy and operation contracts were mixed with migration history.
The browser and index guides mixed UI instructions, database implementation notes,
application defaults and unrelated speech/icon behavior. Markdown and code editing
references mixed user tasks with embedding APIs and repeated sections.

The revised structure keeps `docs/developer/` for cross-cutting integration,
architecture, integration contracts and maintenance guidance. Package references retain
specialized examples. Component-local `user_docs/` guides own reusable user behavior;
flat text/INI modules share `ui/user_docs/`. No Python packages move.

## Evidence and corrections

| Finding | Evidence used / documentation response |
| --- | --- |
| Directory traversal and indexing have different link policies | `filesystem/directories`, `filesystem/traversal.py`, index metadata and traversal tests; document each policy separately |
| File objects are snapshots; object methods and free adapters return different types | File implementation and `test_file_object_operations.py`; explain fresh objects versus boolean adapters |
| Registration is global, reversible and owner-aware | Registry, feature bindings, `test_file_registry.py`, `test_features.py`, and read-only Logistics call sites |
| Public-looking internals are consumed in some projects | Consumer browser adapters; avoid promising blanket stability or declaring all internals disposable |
| No visible browser Pause/Resume control | Browser indexing implementation; distinguish programmatic methods from user controls |
| Cached index data is not a live recursive filesystem view | Scan/reconcile/read implementations and event-driven index tests; document partial/stale results and explicit refresh |
| Markdown guide both supported and denied Mermaid | Renderer, reading extensions and presentation tests; describe explicit local rendering and failure limits |
| Read-aloud start position was outdated | Viewer text provider and read-aloud tests; document selection/visible reading position |
| Wheel defaults confused saved values with fallback values | `ui/settings.ini` versus `configuration/settings.py`; distinguish shipped 100/30 from fallback 20/250 |
| UI guide named a nonexistent process module | `ui/process_progress.py`; correct the import reference |

Source, exports, tests and Logistics call sites were inspected; no Logistics file
was edited. The commonUtils checkout had no AGENTS.md, packaging manifest or
standalone dependency lock. Its CI uses Logistics' environment and isolates test
modules on three OS runners. Blue Hole was not available for independent validation.

## Concerns left unchanged

- `ui/markdown/diagrams.py` mentions restarting Logistics in a reusable missing-tool
  dialog. This application-specific wording is an ownership leak, not a reason to
  describe the renderer as a Logistics feature.
- Diagnostics import the UI facade and retain interactive legacy error paths.
  Headless/work-thread callers need noninteractive logging; a universal exception
  contract cannot be inferred from newer APIs alone.
- Some established consumers import concrete UI/model modules. Their long-term
  stability is not formally specified; changes require consumer checks.
- Cross-platform CI configuration is evidence of intended coverage, not proof of
  current CI success or native speech, shell, trash and window-manager behavior.
- Directory indexes do not track volume identity. Parent scans can prune disconnected
  children; offline retention is not a completed contract.
- Code diff/formatting error text calls a Python-character bound “1 MiB”. The
  documentation records the actual measurement; runtime wording is unchanged.
- No release/version policy or supported dependency range was found. Python 3.10
  syntax alone does not establish a tested Python 3.10 environment.

These are documentation findings; implementation behavior was not changed.

## Validation of this overhaul

- Checked all 274 local Markdown links, including relative files and heading anchors.
- Parsed all 57 Python code blocks in repository Markdown.
- Executed eight examples: root command, initial file listing, two extension examples,
  isolated index snapshot, diagnostics, complete browser construction/cooperative close,
  and the Markdown window event loop/close. GUI examples used offscreen Qt and temporary
  storage; each application example requires its own QApplication lifecycle.
- Passed 191 focused tests across 22 modules: registry, file operations, traversal,
  package layout, features, index policy/reconciliation/search, settings,
  INI/text editors, Markdown/frontmatter/links/presentation, read aloud, code editing,
  diff/merge and workspaces.
- Used the available Python 3.12.2 / PySide6 6.6.2 environment. Qt initially aborted
  during sandbox CPU-feature detection; the same isolated Qt tests passed outside
  that sandbox. Test caches and temporary workspaces were redirected to disposable
  directories rather than the live user index.
- Checked whitespace and documentation-only Git diffs. No Python implementation,
  package directory, settings value or Logistics working-tree file was changed by
  this task. The commonUtils commits naturally change its parent submodule status.

This was focused documentation validation, not a complete native/platform test pass.
Windows/Linux runtime behavior, real speech engines, installed Mermaid CLI output,
external applications, hosted CI and Blue Hole were not independently exercised.

The overhaul consolidates duplicated root/browser examples into the existing feature
guide; moves index migration notes to the
index reference and reader menus/chrome to workspace presentation; removes repeated
code-editor/Markdown summaries; and replaces mixed browser/Markdown narration with
separate integration and user guides. Specialized archive, persistence, format and
process references remain in place.

## Follow-up status (2026-10-22)

The historical findings above describe the documentation audit's source snapshot.
Diagnostics now use an instance-owned GUI-free logger and explicit host presenters;
the [lifecycle guide](lifecycle-owners.md) describes the current contract. Mermaid's
missing-tool message is now application-neutral, and diff/formatting errors label
the existing character bounds accurately. No text limits changed.

Blue Hole is now available for independent consumer checks. Its active development
branch is `blender-5.2.2/alpha`; the 4.5.1 branch remains a legacy snapshot. Host
adapter and vendor-copy tests do not replace live Blender/Perforce validation.
Volume-identity/offline index policy and native platform checks remain separate
open concerns; neither is established by these corrections.
