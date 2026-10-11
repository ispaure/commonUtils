# Documentation audit — October 2026

## Findings and structure

The previous documentation had useful package-local references but no audience-based
entry point. The root README repeated the feature guide's complete browser example;
`_compat.md` combined layout policy, historical migration notes and operation contracts.
The browser and index guides mixed UI instructions, database implementation notes,
application defaults and unrelated speech/icon behavior. Markdown and code editing
references mixed user tasks with embedding APIs and repeated sections.

The revised structure keeps `docs/developer/` for cross-cutting integration,
architecture, compatibility and maintenance guidance. Package references retain
specialized examples. Component-local `user_docs/` guides own reusable user behavior;
flat text/INI modules share `ui/user_docs/`. No Python packages move.

## Evidence and corrections

| Finding | Evidence used / documentation response |
| --- | --- |
| Directory traversal and indexing have different link policies | `filesystem/directories`, `filesystem/traversal.py`, index metadata and traversal tests; document each policy separately |
| File objects are snapshots; object methods and free adapters return different types | File implementation and `test_file_object_operations.py`; explain fresh objects versus boolean adapters |
| Registration is global, reversible and owner-aware | Registry, feature bindings, `test_file_registry.py`, `test_features.py`, and read-only Logistics call sites |
| Public-looking internals are consumed in some projects | Compatibility map and consumer browser adapters; avoid promising blanket stability or declaring all internals disposable |
| No visible browser Pause/Resume control | Browser indexing implementation; distinguish hidden compatibility methods from user controls |
| Cached index data is not a live recursive filesystem view | Scan/reconcile/read implementations and event-driven index tests; document partial/stale results and explicit refresh |
| Markdown guide both supported and denied Mermaid | Renderer, reading extensions and presentation tests; describe explicit local rendering and failure limits |
| Read-aloud start position was outdated | Viewer text provider and read-aloud tests; document selection/visible reading position |
| Wheel defaults confused saved values with fallback values | `ui/settings.ini` versus `configuration/settings.py`; distinguish shipped 100/30 from fallback 20/250 |
| UI guide named a nonexistent process module | `ui/process_progress.py`; correct the import reference |
| Prior layout policy prohibited central docs | Reconcile `_compat.md` with this requested audience-based structure; preserve module references |

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
- No release/version policy or supported dependency range was found. Python 3.10
  syntax compatibility does not establish a tested Python 3.10 environment.

These are documentation findings; implementation behavior was not changed.
