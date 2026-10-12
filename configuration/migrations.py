"""Explicit migration completion outside resettable preferences.

Hosts supply the path, stable versioned IDs and idempotent migration callbacks.
No feature discovery, application paths or GUI imports belong here. Calls should
be serialized by the host; atomic INI publication is not a cross-process lock.
"""
import re
from pathlib import Path
from ..formats.iniType import INIFile


class MigrationLedger:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        ini = INIFile(self.path)
        if self.path.exists():
            ini.read()
        return ini

    @staticmethod
    def _validate(key):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key):
            raise ValueError('Migration IDs must be stable, versioned INI keys')

    def state(self, key):
        self._validate(key)
        value = self._read().get('Migrations', key)
        if value not in (None, 'pending', 'done'):
            raise ValueError(f'Invalid migration state for {key}; ledger preserved')
        return value

    def complete(self, *keys):
        ini = self._read()
        for key in keys:
            self._validate(key)
            ini.set('Migrations', key, 'done')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        ini.save()

    def run(self, key, migrate, *, already_applied=False):
        """Run once, or adopt an old completion marker. Return whether work ran.

        Pending is published before calling the host. A failed/partial migration
        retries even when it created a destination file, so callbacks must be
        idempotent. Parse/I/O errors preserve the ledger and propagate.
        """
        state = self.state(key)
        if state == 'done':
            return False
        if state is None and already_applied:
            self.complete(key)
            return False
        ini = self._read()
        ini.set('Migrations', key, 'pending')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        ini.save()
        migrate()
        self.complete(key)
        return True
