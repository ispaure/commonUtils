# Shared-library regression tests

Filesystem/archive tests use temporary fixtures; Qt tests use an offscreen application and retire their owned windows and workers. Tests do not need a production Perforce server.

From Logistics, run `QT_QPA_PLATFORM=offscreen PYTHONPATH=Python .venv/bin/python Python/tests/run_regressions.py Python/commonUtils/tests`. Standalone consumers can use unittest discovery with the repository parent on PYTHONPATH.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [qt_test_case.py](qt_test_case.py) | Give every Qt test ownership of its windows and background workers. |
| [test_archive_types.py](test_archive_types.py) | Archive formats use shared file resolution and passive detail hooks. |
| [test_archive_view.py](test_archive_view.py) | The shared archive view emits requests, independently of application policy. |
| [test_archives.py](test_archives.py) | Verified creation/editing and transactional, traversal-safe extraction. |
| [test_browser_file_actions.py](test_browser_file_actions.py) | Default browser editing works across views and interoperates with file clipboards. |
| [test_browser_index_policy.py](test_browser_index_policy.py) | Navigation stays local; explicit refresh scans deeper and saved branches remain usable. |
| [test_browser_polish.py](test_browser_polish.py) | Breadcrumb geometry and bounded, optional radial navigation transitions. |
| [test_browser_presentation.py](test_browser_presentation.py) | Selection preview and private status presentation, using real Qt widgets. |
| [test_browser_size_sort.py](test_browser_size_sort.py) | Displayed byte totals drive ordering, independently of formatted labels. |
| [test_bulk_rename.py](test_bulk_rename.py) | Filename transformations and no-overwrite/rollback behavior on real temporary files. |
| [test_code_diff.py](test_code_diff.py) | `DiffTests` |
| [test_code_editor.py](test_code_editor.py) | `CodeEditorTests` |
| [test_code_folding.py](test_code_folding.py) | `FoldingTests` |
| [test_code_formatting.py](test_code_formatting.py) | `FormattingTests` |
| [test_code_multicursor.py](test_code_multicursor.py) | `MultiCursorTests` |
| [test_code_search.py](test_code_search.py) | `CodeSearchTests` |
| [test_code_syntax.py](test_code_syntax.py) | `SyntaxTests` |
| [test_code_transforms.py](test_code_transforms.py) | `TransformTests` |
| [test_commands.py](test_commands.py) | Real child-process outcomes, argument boundaries, timeouts and cancellation. |
| [test_directory_exclusions.py](test_directory_exclusions.py) | Synthetic macOS firmlink layout: never traverse the Data alias from /. |
| [test_directory_index.py](test_directory_index.py) | `DirectoryIndexTests` |
| [test_directory_reconcile.py](test_directory_reconcile.py) | Visible-folder updates remain bounded and retain immutable old read snapshots. |
| [test_directory_schema.py](test_directory_schema.py) | Compact index migration, shared versions, and recovery against real SQLite. |
| [test_directory_search_terms.py](test_directory_search_terms.py) | Keyword/phrase matching stays identical for SQL and detached snapshots. |
| [test_discovery_index_ui.py](test_discovery_index_ui.py) | Storage communicates saved checkpoints and supports rebuilding. |
| [test_downloads.py](test_downloads.py) | Verified provisioning preserves existing files on failure/cancellation. |
| [test_entry_views.py](test_entry_views.py) | Unknown byte sizes stay last in both Qt sorting directions. |
| [test_event_driven_index.py](test_event_driven_index.py) | Completed browsers stay idle; visits check one folder and Refresh checks deeper. |
| [test_features.py](test_features.py) | Unified declarations bind actions without service-name wiring. |
| [test_file_browser.py](test_file_browser.py) | Reusable browser works with generic files and independently registered types. |
| [test_file_moves.py](test_file_moves.py) | Run from the parent directory: python3 -m unittest discover -s commonUtils/tests. |
| [test_file_operations.py](test_file_operations.py) | Clipboard transfer semantics preserve originals, links and existing destinations. |
| [test_file_registry.py](test_file_registry.py) | Global registration, priority, built-ins and Directory listing compatibility. |
| [test_file_removal.py](test_file_removal.py) | Removal never follows links or silently escalates trash failures. |
| [test_icons.py](test_icons.py) | Painted icon copies survive garbage collection and update with the palette. |
| [test_index_efficiency.py](test_index_efficiency.py) | Discovery ordering, durable checkpoints and aggregate write amplification. |
| [test_index_folder_sizes.py](test_index_folder_sizes.py) | Index aggregates, cached reads and incomplete recursive size semantics. |
| [test_ini_file.py](test_ini_file.py) | Generic INI parsing, format retention and conflict-safe saves. |
| [test_ini_settings.py](test_ini_settings.py) | Typed INI settings stay Logistics-owned and preserve explicit-save behavior. |
| [test_integrated_index_search.py](test_integrated_index_search.py) | Automatic indexing, recursive cached queries, watcher updates and normal actions. |
| [test_json_type.py](test_json_type.py) | Reusable JSON files preserve originals when serialization or replacement fails. |
| [test_launcher_pause.py](test_launcher_pause.py) | Launcher pause flags must work with macOS's bundled Bash 3.2. |
| [test_managed_index_views.py](test_managed_index_views.py) | Storage and inline search consume automatic browser indexing without rescanning. |
| [test_markdown.py](test_markdown.py) | Markdown rendering, local link history, failures and browser activation. |
| [test_markdown_frontmatter.py](test_markdown_frontmatter.py) | YAML properties and lossless frontmatter across formatted Markdown edits. |
| [test_markdown_links.py](test_markdown_links.py) | Shared link syntax, live edit round trips, and centralized Alt permission. |
| [test_markdown_live_edit.py](test_markdown_live_edit.py) | Live typed Markdown, selection wrapping and editor document/undo boundaries. |
| [test_markdown_presentation.py](test_markdown_presentation.py) | Reading extensions remain presentation-only and use palette-aware formats. |
| [test_markdown_tables.py](test_markdown_tables.py) | Table structure editing, undo, Markdown publication and preview boundaries. |
| [test_network_filesystems.py](test_network_filesystems.py) | Classify shares from mount metadata and keep network traversal out of indexes. |
| [test_notifications.py](test_notifications.py) | `NoticeTests` |
| [test_operations.py](test_operations.py) | Shared task progress publishes results on the GUI thread after worker shutdown. |
| [test_outline.py](test_outline.py) | Outline presentation never interprets navigation targets as filesystem paths. |
| [test_package_compatibility.py](test_package_compatibility.py) | Legacy imports must share implementation state after package reorganization. |
| [test_page_wheel.py](test_page_wheel.py) | Shared reader wheel gesture policy, including live INI changes. |
| [test_persistence.py](test_persistence.py) | Publication races and staging cleanup, independent of text format policy. |
| [test_persistent_directory_index.py](test_persistent_directory_index.py) | Durable folder checkpoints, snapshot isolation and incremental directory updates. |
| [test_process_progress.py](test_process_progress.py) | `ProcessTests` |
| [test_pyside_compatibility.py](test_pyside_compatibility.py) | The organized Qt package keeps the historical facade and customization hooks. |
| [test_radial_rendering.py](test_radial_rendering.py) | Radial redraw cost, geometric hit testing and cursor-following hover details. |
| [test_read_aloud.py](test_read_aloud.py) | Speech queue/lifetime tests use a silent engine, never the user's speakers. |
| [test_reader_chrome.py](test_reader_chrome.py) | Native window-state synchronization and shared reader layout boundaries. |
| [test_reader_menus.py](test_reader_menus.py) | Recent-file persistence and shared menu dispatch are format independent. |
| [test_result_worker.py](test_result_worker.py) | `ResultWorkerTests` |
| [test_search_columns.py](test_search_columns.py) | Search layouts prioritize names, including narrow tabs and long extensions. |
| [test_session_store.py](test_session_store.py) | `SessionStoreTests` |
| [test_settings.py](test_settings.py) | Shared typed settings tolerate bad INIs and reflect explicitly saved edits. |
| [test_shared_index_jobs.py](test_shared_index_jobs.py) | Browser subscriptions share work, progress, and independent cancellation. |
| [test_storage_browser_view.py](test_storage_browser_view.py) | Storage uses saved index data, browser navigation and shared selection. |
| [test_storage_paths.py](test_storage_paths.py) | OS conventions, scoped cleanup and WAL-safe index migration. |
| [test_streams.py](test_streams.py) | Shared stream helpers retain byte integrity and stop at cooperative boundaries. |
| [test_text_commands.py](test_text_commands.py) | `TextCommandTests` |
| [test_text_editor.py](test_text_editor.py) | Plain-text saves preserve file conventions and refuse to overwrite external edits. |
| [test_text_files.py](test_text_files.py) | `TextFilesTests` |
| [test_theme.py](test_theme.py) | Opt-in theme, accessible palettes and active workspace tab rendering. |
| [test_tile_icons.py](test_tile_icons.py) | Small raster icons are enlarged and centered independently of native style. |
| [test_traversal.py](test_traversal.py) | Filtered traversal preserves its depth, link and cancellation contracts. |
| [test_workspace.py](test_workspace.py) | Compact native tab headers, cooperative closing, docking and view transfers. |
| [test_xml.py](test_xml.py) | Generic DOM XML workflows and lossless legacy field compatibility. |
| [test_zip_access.py](test_zip_access.py) | Plain/AES content parity, authentication and failure-safe archive operations. |
| [test_zip_paths.py](test_zip_paths.py) | Verify ZIP members remain within the selected extraction directory. |

[Parent guide](../README.md)
