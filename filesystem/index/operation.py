"""Transient state for one scan, reconciliation or exclusion-repair writer."""
from dataclasses import dataclass, field
from pathlib import Path
from time import time


def scan_metrics():
    return dict(metadata_seconds=0., database_write_seconds=0., aggregation_seconds=0.,
                validation_seconds=0., checkpoint_seconds=0., checkpoints=0)


@dataclass
class ScanState:
    """Created under a writer lease; never reused by the next operation.

    Invalidations, visible-folder priorities and reader ownership belong to the
    cache session. Durable generations/checkpoints belong to SQLite. Only the
    mutable counters and pending sets for the current attempt live here.
    """
    excluded_paths: tuple[Path, ...] = ()
    discovered_entries: int = 0
    checked_entries: int = 0
    blocked_folders: set[Path] = field(default_factory=set)
    dirty_totals: set[Path] = field(default_factory=set)
    checkpoint_entries: int = 0
    checkpoint_at: float = field(default_factory=time)
    totals_last: float = field(default_factory=time)
    totals_interval: float = 2
    metrics: dict = field(default_factory=scan_metrics)

    def blocks(self, folder):
        return folder in self.blocked_folders or any(parent in self.blocked_folders for parent in folder.parents)
