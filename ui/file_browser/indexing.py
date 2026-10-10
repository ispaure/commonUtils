"""Browser index jobs, cached totals and progress presentation."""
from datetime import datetime
from pathlib import Path
from ...dirUtils import Directory
from .index_worker import FolderOperation
from .. import pyside as qt


class IndexPriorityLease(qt.QObject):
    """Release priority through a native QObject slot during parent destruction."""
    def __init__(self, parent, cache, owner):
        super().__init__(parent)
        self.cache, self.owner = cache, owner
        parent.destroyed.connect(self.release)

    @qt.Slot()
    def release(self):
        self.cache.set_priority_folders(self.owner)


class BrowserIndexing:
    def refresh_item(self, path):
        self._changed_paths.add(Path(path).parent)
        self.model.invalidate(path)
        self.views.covers.invalidate(path)
        if self.selected_object is not None and self.selected_object.path == Path(path):
            self._selection_changed()
        self.refresh_folder_totals()

    def refresh(self):
        if self.network_location:
            return
        from ...directory import directory_cache
        directory_cache.invalidate(self.navigation.directory)
        self._full_index_refresh = True
        self._index_paused = False
        for path in list(self.views.covers.icons):
            self.model.invalidate(path)
            self.views.covers.invalidate(path)
        self.refresh_folder_totals()
        self._selection_changed()
        self.refreshed.emit()

    def set_folder_sizes_enabled(self, enabled):
        """Pause/resume automatic index totals without blocking on a running scan."""
        self.calculate_folder_sizes = bool(enabled)
        if not enabled:
            self.folder_pending = False
            self.index_activity.hide()
            if self.folder_busy:
                self.folder_operation.requestInterruption()
            self._index_progressed('Indexing paused; cached results remain available.')
        else:
            self.refresh_folder_totals()
        if isinstance(self.selected_object, Directory):
            self._selection_changed()

    def refresh_changed(self, paths=()):
        """Reconcile known file-operation changes without revalidating the tree."""
        self._changed_paths.update(Path(path) for path in paths or (self.navigation.directory,))
        self.refresh_folder_totals()
        self._selection_changed()
        self.refreshed.emit()

    def _toggle_index_pause(self):
        self._index_paused = not self._index_paused
        if self._index_paused:
            self.folder_pending = False
            self.reconcile_debounce.stop()
            if self.folder_busy:
                self._changed_paths.update(self._active_index_changes)
                self._full_index_refresh |= self._active_index_full
                self.folder_operation.requestInterruption()
            self.index_status.setText('Indexing paused · Saved search and sizes available')
            self.index_progress.emit(self.index_status.text())
        else:
            self.refresh_folder_totals()
        self._update_pause_button()

    def _update_pause_button(self):
        self.index_details_button.setVisible(self.index_incomplete and not getattr(self, 'workspace_status', False))
        self.refresh_button.setVisible(not self.folder_busy and not getattr(self, 'workspace_status', False))
        self.refresh_button.setEnabled(self.calculate_folder_sizes and not self.network_location and self.navigation.directory is not None)
        self.index_pause_button.setText('Resume' if self._index_paused else 'Pause')
        self.index_pause_button.hide()

    def refresh_folder_totals(self):
        if not self.calculate_folder_sizes or self.network_location:
            return
        root = self.navigation.directory
        if self.folder_busy:
            if (root is not None and not self._index_paused and not self._full_index_refresh
                    and not self._active_index_full and not self._changed_paths and not self.folder_pending
                    and self.folder_operation.retarget(root)):
                self.folder_root = root
                return
            self.folder_pending = True
            self._changed_paths.update(self._active_index_changes)
            self._full_index_refresh |= self._active_index_full
            self.folder_operation.requestInterruption()
            return
        if root is None or self.stopping:
            return
        from ...directory import directory_cache
        from ...operations import OperationCancelled
        full = self._full_index_refresh
        paused = self._index_paused
        changes = tuple(sorted(self._changed_paths))
        from .index_policy import index_policy
        policy = index_policy(path=self.index_settings_path)
        read_cache = paused or not full and not changes and (not policy.scan_on_open or not policy.refresh_cached_on_startup)
        cached_only = read_cache or not full and not changes and directory_cache.was_checked_this_session(root)
        self._loading_cached_only = cached_only
        if not paused:
            self._full_index_refresh = False
            self._changed_paths.clear()
            self._reconcile_pending = False
        self._active_index_changes = changes if not paused else ()
        self._active_index_full = full and not paused
        self._active_index_recursive = full or policy.recursive_on_open
        self.folder_busy = True
        self.index_activity.setVisible(not cached_only and not getattr(self, 'workspace_status', False))
        self.folder_pending = False
        same_root = self.folder_root == root
        self.folder_root = root
        self._update_pause_button()
        if not cached_only or not same_root:
            self.index_status.setText('Loading saved sizes…' if cached_only else 'Checking saved index…')
        def scanner(path, cancelled, *, report, reuse_for):
            try:
                if read_cache:
                    if not paused:
                        directory_cache.repair_cached_exclusions(path, cancelled=cancelled, report=report)
                    snapshot = directory_cache.peek(path, cancelled=cancelled)
                else:
                    snapshot = None
                if not read_cache or snapshot is None and not paused and policy.scan_on_open:
                    snapshot = directory_cache.reconcile_folder(path, changes=changes, full=full, once=True,
                                                               cancelled=cancelled, report=report,
                                                               recursive_initial=policy.recursive_on_open)
                return snapshot.folder_stats(children_of=path, cancelled=cancelled) if snapshot else None
            except OperationCancelled:
                return None
        self.folder_operation = FolderOperation(root, scanner, self,
            request_key=('cached' if read_cache else 'full' if full else 'reconcile', changes),
            background_priority=policy.background_priority)
        self.folder_operation.updated.connect(self._folders_progressed)
        self.folder_operation.progress.connect(lambda message: self._index_progressed(message)
                                               if self.folder_root == self.navigation.directory else None)
        self.folder_operation.watch_paths.connect(self._update_watch_paths)
        self.folder_operation.completed.connect(lambda result, error: self._folders_loaded(self.folder_operation.visible_root, result, error))
        self.folder_operation.finished.connect(self._folders_finished)
        self.folder_operation.start()
        if self.folder_operation.root != root:
            self._loading_cached_only = False
            self.index_activity.setVisible(not getattr(self, 'workspace_status', False))
            self._update_pause_button()
        self.index_state_changed.emit()

    def _folders_progressed(self, root, result):
        if self.calculate_folder_sizes and not self.network_location and root == self.navigation.directory and result and not self.folder_pending and not self.stopping:
            if self.model.folder_totals == result:
                return
            self.model.set_folder_totals(result)
            self.index_search.refresh()
            self.index_updated.emit(root)
            if not self.folder_busy:
                self.index_status.setText('Cached or partial sizes available.')
            if (isinstance(self.selected_object, Directory) and not self.refresh_pending
                    and self._preview_enabled() and not self.preview_panel.isHidden()):
                self.load(self.selected_object, preserve=True)

    def _folders_loaded(self, root, result, error=''):
        if error and root == self.navigation.directory and not self.stopping:
            self.index_status.setText('Index unavailable. Any cached sizes remain available; refresh to retry.')
            self.index_progress.emit(self.index_status.text())
        if self.calculate_folder_sizes and not self.network_location and root == self.navigation.directory and result is not None and not self.folder_pending and not self.stopping:
            changed = self.model.folder_totals != result
            self.model.set_folder_totals(result)
            self.index_search.refresh()
            stats = result.get(root)
            self.index_incomplete = stats is not None and not stats.complete
            self.index_details_button.setVisible(self.index_incomplete and not getattr(self, 'workspace_status', False))
            checked = datetime.fromtimestamp(stats.scanned_at).strftime('%b %d at %H:%M:%S') if stats else 'just now'
            if self._index_paused:
                message = f'Indexing paused · Saved sizes · Last checked {checked}'
            elif stats is not None and not stats.complete:
                message = ('Visible contents indexed · Subtree sizes are partial · Refresh index scans deeper'
                           if not self._active_index_recursive else
                           'Index incomplete · Index details shows unfinished work · Refresh to retry')
            elif stats is not None and stats.stale:
                message = f'Folder last checked {checked} · Saved subtree sizes · Refresh checks deeper contents'
            else:
                message = f'Index and sizes up to date · Checked {checked}'
            self.index_status.setText(message)
            if changed:
                self.index_updated.emit(root)
            self.index_progress.emit(self.index_status.text())
            if (changed and isinstance(self.selected_object, Directory) and not self.refresh_pending
                    and self._preview_enabled() and not self.preview_panel.isHidden()):
                self.load(self.selected_object, preserve=True)

    def _index_progressed(self, message):
        from .status import private_status
        message = private_status(message)
        if self.network_location or self.folder_busy and getattr(self, '_loading_cached_only', False):
            return
        if not self.stopping and self.calculate_folder_sizes and not self._index_paused:
            self.index_status.setText(message)
            self.index_progress.emit(message)
        elif message.startswith('Indexing paused'):
            self.index_status.setText(message)
            self.index_progress.emit(message)

    def show_index_details(self):
        if self.network_location:
            return None
        from .index_details import IndexDetailsDialog
        if self._index_details_dialog is None:
            self._index_details_dialog = IndexDetailsDialog(self)
            self._index_details_dialog.destroyed.connect(self._index_details_closed)
        self._index_details_dialog.show()
        self._index_details_dialog.raise_()

    def _index_details_closed(self):
        self._index_details_dialog = None

    def _folders_finished(self):
        self.folder_busy = False
        self.index_activity.hide()
        self.index_state_changed.emit()
        self._update_pause_button()
        self.folder_operation.deleteLater()
        if self.stopping:
            self._maybe_idle()
        elif (self.folder_operation.visible_root != self.folder_operation.root
              and not self._index_paused and not self.folder_pending and not self._reconcile_pending):
            from ...directory import directory_cache
            if not directory_cache.was_checked_this_session(self.navigation.directory):
                self.refresh_folder_totals()
            else:
                self.index_search.refresh()
        elif self.folder_pending or (self._reconcile_pending and not self._index_paused):
            self._reconcile_pending = False
            self.refresh_folder_totals()
        else:
            self.index_search.refresh()

