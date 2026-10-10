"""Scan-generation orchestration, discovery passes and publication."""
import os
from pathlib import Path
from time import time
from .operations import check_cancelled
from ._directory_schema import retire_generation, copy_entries
from ._directory_exclusions import scan_exclusions
from ._directory_totals import store_folder_stats


class DirectoryScan:
    def get(self, root, recursive=True, *, refresh=False, cancelled=lambda: False,
            report=lambda done, total, message: None, validate_files=True, reuse_for=0, retry_errors=True):
        root = Path(root).absolute()
        if not root.is_dir():
            raise NotADirectoryError(root)
        if root.resolve() == self.database.parent.resolve():
            raise ValueError('The directory index storage folder cannot index itself. Choose another folder.')
        report(0, 0, 'Waiting for index writer…')
        with self._writer(cancelled, report) as db:
            self._discovered_entries = self._checked_entries = 0
            self._blocked_scan_folders = set()
            self._dirty_totals = set()
            self._checkpoint_entries = 0
            self._checkpoint_at = time()
            self.last_metrics = dict(metadata_seconds=0.,database_write_seconds=0.,aggregation_seconds=0.,validation_seconds=0.,checkpoint_seconds=0.,checkpoints=0)
            self._totals_interval = 2
            with self._state_lock:
                revision = self._revision
                checked_revision = self._validated_roots.get((root, recursive), 0)
                dirty = any(mark > checked_revision and (path is None or path == root or path in root.parents or root in path.parents)
                            for path, mark in self._invalidations.items())
            self._totals_last = time()
            self._excluded_paths = scan_exclusions(root, self.database)
            db.execute('INSERT OR IGNORE INTO roots(root,recursive) VALUES(?,?)', (str(root), recursive))
            completed, building = db.execute('SELECT completed,building FROM roots WHERE root=? AND recursive=?', (str(root), recursive)).fetchone()
            for generation in (completed, building):
                if generation:
                    self._repair_exclusions(db, generation, root, cancelled, report)
            db.commit()
            if recursive and not completed and not building and not refresh and reuse_for:
                # Navigation can read a freshly validated ancestor directly; no work
                # generation, metadata pass or duplicate subtree rows are needed.
                ancestors = tuple(str(path) for path in root.parents)
                if ancestors:
                    candidates = db.execute('SELECT root,completed FROM roots WHERE recursive=1 AND building IS NULL '
                                            'AND completed IS NOT NULL AND root IN ('+', '.join('?' for _ in ancestors)+') '
                                            'ORDER BY length(root) DESC',ancestors).fetchall()
                    for source_text,source in candidates:
                        source_root = Path(source_text)
                        with self._state_lock:
                            stamp = self._validated_times.get((source_root,True),0)
                            checked = self._validated_roots.get((source_root,True),0)
                            changed = any(mark>checked and (path is None or path==root or path in root.parents or root in path.parents)
                                          for path,mark in self._invalidations.items())
                            fresh = time()-stamp<reuse_for and not changed
                        if fresh:
                            report(0,0,'Using recently checked ancestor index…')
                            return self._snapshot(db,source,root,True,reused=True,scope=root,cancelled=cancelled)
            if recursive and not completed and not building and not refresh:
                # Seed a newly browsed subtree from completed or partial ancestor checkpoints.
                # Validation still checks every descendant before reuse, but names
                # and unchanged folders need no second filesystem enumeration.
                ancestors = tuple(str(path) for path in root.parents)
                if ancestors:
                    covering = db.execute('SELECT coalesce(building,completed),building IS NOT NULL FROM roots '
                                          'WHERE recursive=1 AND (completed IS NOT NULL OR building IS NOT NULL) '
                                          'AND root IN (' + ','.join('?' for _ in ancestors) + ') ORDER BY length(root) DESC LIMIT 1', ancestors).fetchone()
                    if covering:
                        report(0, 0, 'Reusing saved subtree checkpoints…')
                        seed = db.execute('INSERT INTO scans(root,recursive,scanned_at) '
                                          'SELECT ?,1,scanned_at FROM scans WHERE id=?', (str(root), covering[0])).lastrowid
                        prefix = str(root).rstrip(os.sep) + os.sep
                        upper = prefix[:-1] + chr(ord(os.sep) + 1)
                        copy_entries(db, seed, covering[0], scope=root)
                        db.execute('INSERT INTO folders SELECT ?,path,parent,status,identity FROM folders WHERE generation=? '
                                   'AND (path=? OR (path>=? AND path<?))', (seed, covering[0], str(root), prefix, upper))
                        db.execute('INSERT INTO errors SELECT ?,path,error FROM errors WHERE generation=? '
                                   'AND (path=? OR (path>=? AND path<?))', (seed, covering[0], str(root), prefix, upper))
                        if not db.execute('SELECT 1 FROM folders WHERE generation=? AND path=?', (seed, str(root))).fetchone():
                            db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL)", (seed, str(root), ''))
                        imported = self._seed_descendants(db, seed, root, cancelled, report)
                        self._repair_exclusions(db, seed, root, cancelled, report)
                        if covering[1] or imported:
                            building = seed
                            db.execute('UPDATE roots SET building=? WHERE root=? AND recursive=1', (seed, str(root)))
                        else:
                            completed = seed
                            db.execute('UPDATE roots SET completed=? WHERE root=? AND recursive=1', (seed, str(root)))
                        if imported:
                            store_folder_stats(db, seed, root, cancelled)
                        db.commit()
                        if imported:
                            report(0, 0, 'Saved progressive folder totals')
            with self._state_lock:
                recently_checked = time() - self._validated_times.get((root, recursive), 0) < reuse_for
            if completed and not building and not refresh and not dirty and recently_checked:
                return self._snapshot(db, completed, root, recursive, reused=True, cancelled=cancelled)

            if not recursive and not completed and not building and not refresh and not dirty:
                full = db.execute('SELECT completed FROM roots WHERE root=? AND recursive=1', (str(root),)).fetchone()
                if full and full[0] and self._validate(db, full[0], root, cancelled, report, root_only=True, check_files=validate_files):
                    return self._snapshot(db, full[0], root, False, reused=True, parent=root, metadata_checked=validate_files, cancelled=cancelled)
            if completed and not building and not refresh and not dirty:
                if self._validate(db, completed, root, cancelled, report, check_files=validate_files):
                    if validate_files:
                        with self._state_lock:
                            self._validated_times[(root, recursive)] = time()
                    return self._snapshot(db, completed, root, recursive, reused=True, metadata_checked=validate_files, cancelled=cancelled)
            resumed = bool(building) and not refresh
            if refresh and building:
                retire_generation(db, building)
                building = None
            # Validate on disk using one folder at a time. A completed generation is
            # immutable for readers, so validation/status changes happen in a work copy.
            if not building:
                building = db.execute('INSERT INTO scans(root,recursive) VALUES(?,?)', (str(root), recursive)).lastrowid
                if completed and not refresh:
                    copy_entries(db, building, completed)
                    db.execute('INSERT INTO folders SELECT ?,path,parent,status,identity FROM folders WHERE generation=?', (building, completed))
                    db.execute('INSERT INTO folder_totals SELECT ?,path,size,files,folders,skipped,extensions,complete,scanned_at FROM folder_totals WHERE generation=?',(building,completed))
                else:
                    db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL)", (building, str(root), ''))
                db.execute('UPDATE roots SET building=? WHERE root=? AND recursive=?', (building, str(root), recursive))
                if recursive and not completed and not refresh:
                    # A new higher starting point can reuse independently indexed branches.
                    # Prefer more specific checkpoints when cached scopes overlap.
                    covered = self._seed_descendants(db, building, root, cancelled, report)
                    self._repair_exclusions(db, building, root, cancelled, report)
                    if covered:
                        resumed = True
                        store_folder_stats(db, building, root, cancelled)
                db.commit()
                if resumed:
                    report(0, 0, 'Saved progressive folder totals')
            db.execute('CREATE TEMP TABLE scan_blocked(path TEXT PRIMARY KEY)')
            if not retry_errors:
                # Saved directory failures require explicit retry. Missing work
                # from cancellation remains eligible for normal resume.
                self._blocked_scan_folders = {Path(path) for (path,) in db.execute(
                    'SELECT f.path FROM folders f JOIN errors e ON e.generation=f.generation AND e.path=f.path '
                    'WHERE f.generation=?', (building,))}
                for folder in self._blocked_scan_folders:
                    self._block_scan_tree(db, building, folder)
            # Finish discovering missing branches before rechecking old metadata.
            # Completed folders are validated after discovery, including on resume.
            unchanged = False
            if not resumed and completed:
                unchanged = self._validate(db, building, root, cancelled, report)
            if unchanged and completed and not resumed and not dirty and not refresh:
                db.execute('UPDATE roots SET building=NULL WHERE root=? AND recursive=?', (str(root), recursive))
                retire_generation(db, building)
                db.commit()
                return self._snapshot(db, completed, root, recursive, reused=True, cancelled=cancelled)
            report(0, 0, 'Resuming saved folder checkpoints…' if resumed else 'Updating persistent index…')
            self._discover_pending(db, building, root, recursive, cancelled, report)
            check_cancelled(cancelled)
            valid = self._validate(db, building, root, cancelled, report)
            if resumed and not valid:
                # Only a failed verification needs a repair pass and recheck.
                repaired = self._discover_pending(db, building, root, recursive, cancelled, report)
                if repaired:
                    valid = self._validate(db, building, root, cancelled, report)
            return self._finish_scan(db, building, completed, root, recursive, valid, resumed, revision, cancelled)

    def _discover_pending(self, db, building, root, recursive, cancelled, report):
        # A live directory may change on every enumeration. Give each
        # folder one attempt per pass; retain unstable checkpoints for
        # explicit retry instead of feeding them back forever.
        db.execute('CREATE TEMP TABLE IF NOT EXISTS scan_visited(path TEXT PRIMARY KEY)')
        db.execute('DELETE FROM scan_visited')
        handled_priorities, visited_priorities = set(), set()
        attempted = 0
        while True:
            check_cancelled(cancelled)
            # Batches avoid sorting the whole pending tree for every folder.
            rows = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' AND identity IS NULL AND path NOT IN (SELECT path FROM scan_visited) AND path NOT IN (SELECT path FROM scan_blocked) ORDER BY length(path),path LIMIT 256", (building,)).fetchall()
            if not rows:
                rows = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' AND path NOT IN (SELECT path FROM scan_visited) AND path NOT IN (SELECT path FROM scan_blocked) ORDER BY length(path),path LIMIT 256", (building,)).fetchall()
            if not rows:
                break
            for (path,) in rows:
                check_cancelled(cancelled)
                while priority := self._next_priority_folder(db, building, root, handled_priorities, visited_priorities):
                    check_cancelled(cancelled)
                    folder, visible = priority
                    visited_priorities.add(folder)
                    db.execute('INSERT OR IGNORE INTO scan_visited VALUES(?)', (str(folder),))
                    self._scan_folder(db, building, root, recursive, folder, cancelled, report)
                    attempted += 1
                    # Publish a visible folder promptly even during a long
                    # first scan, without changing its original scan root.
                    if visible:
                        self._publish_totals(db, building, root, cancelled)
                        self._checkpoint(db, cancelled, force=True)
                        report(0, 0, 'Saved progressive folder totals')
                # A parent reconciliation can remove a previously queued child.
                if db.execute("SELECT 1 FROM folders WHERE generation=? AND path=? AND status='pending' AND path NOT IN (SELECT path FROM scan_visited) AND path NOT IN (SELECT path FROM scan_blocked)", (building, path)).fetchone():
                    db.execute('INSERT OR IGNORE INTO scan_visited VALUES(?)', (path,))
                    self._scan_folder(db, building, root, recursive, Path(path), cancelled, report)
                    attempted += 1
        return attempted

    def _finish_scan(self, db, building, completed, root, recursive, valid, resumed, revision, cancelled):
        errors = db.execute('SELECT count(*) FROM errors WHERE generation=?', (building,)).fetchone()[0]
        self._publish_totals(db,building,root,cancelled)
        db.execute('INSERT OR REPLACE INTO folder_checks VALUES(?,?,?)', (building, str(root), time()))
        db.execute('UPDATE scans SET scanned_at=? WHERE id=?', (time(), building))
        complete = valid and not errors
        with self._state_lock:
            visible_roots = tuple(path for paths in self._priority_folders.values() for path in paths)
        checked = [path for path in visible_roots if (path == root or root in path.parents) and
                       db.execute("SELECT 1 FROM folders WHERE generation=? AND path=?",
                                  (building,str(path))).fetchone()]
        if complete:
            db.execute('UPDATE roots SET completed=?,building=NULL WHERE root=? AND recursive=?', (building, str(root), recursive))
            if completed:
                retire_generation(db, completed)
        db.commit()
        with self._state_lock:
            # A finished attempt is terminal even when some folders were
            # unreadable/unstable. Cancellation never reaches this point.
            self._session_checked.update((self.database,path) for path in (root,*checked))
            if revision == self._revision and complete:
                self._validated_roots[(root, recursive)] = revision
                self._validated_times[(root, recursive)] = time()
        return self._snapshot(db, building, root, recursive, resumed=resumed, complete=complete, cancelled=cancelled)
