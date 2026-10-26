# Process, diagnostics and presentation owners

## Processes

`integrations.wrappers.cmdShellWrapper.process.ProcessSupervisor` owns one child
process tree and its I/O worker threads. Binary streaming, text command results
and bounded disk-backed capture retain their distinct buffering, deadline and
result contracts. Start workers through the supervisor inside its context; an
exception, live child or unfinished worker triggers process-tree termination.
Worker startup failure is covered as well. Cleanup joins started workers and
closes subprocess streams. It cannot forcibly interrupt arbitrary Python callbacks.

## Diagnostics

`runtime.diagnostics.DebugLogger` owns `LoggingOptions`, sinks, timestamp state,
presentation callback and critical failure policy. `ConsoleSink` and `FileSink`
consume immutable `LogEvent` values. Independent instances do not share prefixes
or timing state. Configure the namespace-local default with
`runtime.diagnostics.configure(...)`; module-global option assignments are obsolete.

The runtime imports no UI. A desktop host may explicitly configure
`presenter=commonUtils.ui.diagnostics.present_diagnostic` once Qt exists. Mobile
and background consumers can retain the default without presentation. Critical
messages still raise `DebugException` unless an independent logger explicitly sets
`raise_critical=False`. `noninteractive_logging()` suppresses presentation without
changing severity, sinks or the critical exception policy.

## Qt presentation

`ui.file_browser.assembly.BrowserControls` builds navigation, views, preview and
layout. `FileBrowser` retains behavior, indexing, worker shutdown and extension
ownership. `ui.workspaces.presentation.WorkspaceHeaderPresentation` owns tab/header
projection and pending refresh state; `Workspace` retains sources and lifetime.
These owners access their host instance explicitly rather than adding forwarding
methods for the removed private construction and refresh entry points.

Regression coverage includes process worker startup failure, exited parents,
independent logger configuration and presentation policy, browser behavior and
workspace refresh coalescing. Native Windows process-tree behavior still needs
platform validation.
