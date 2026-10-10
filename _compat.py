"""Lazy legacy imports, scoped to this copy of commonUtils.

Aliases return the canonical module itself, including nested packages, so caches,
classes and monkey-patches cannot diverge. No optional GUI dependency is loaded
until a consumer imports it. This also works inside Blue Hole's vendored package.
"""
from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_loader
import sys

ALIASES = {
    'appUtils': 'integrations.applications',
    'configUtils': 'configuration.legacy',
    'debugUtils': 'runtime.diagnostics',
    'dirUtils': 'filesystem.directories',
    'directory': 'filesystem.index',
    'directory_index': 'filesystem.index',
    'downloads': 'runtime.streams.downloads',
    'features': 'ui.features',
    'fileTypes': 'formats',
    'fileUtils': 'filesystem.files',
    'file_operations': 'filesystem.transfers',
    'file_removal': 'filesystem.removal',
    'linkUtils': 'filesystem.links',
    'logUtils': 'runtime.logging',
    'marcUtils': 'runtime.helpers',
    'markdownUtils': 'formats.markdown',
    'network_filesystems': 'filesystem.network',
    'operations': 'runtime.operations',
    'osUtils': 'runtime.platform',
    'pySideUtils': 'ui.pyside',
    'renameUtils': 'filesystem.rename',
    'session_store': 'persistence.session',
    'settings': 'configuration.settings',
    'spreadsheetUtils': 'formats.spreadsheets',
    'steamUtils': 'integrations.steam',
    'storage': 'filesystem.storage',
    'streams': 'runtime.streams',
    'text_files': 'persistence.text',
    'text_merge': 'persistence.merge',
    'traversal': 'filesystem.traversal',
    'webUtils': 'integrations.web',
    'wrappers': 'integrations.wrappers',
    'zipUtils': 'archives.legacy',
    'zip_access': 'archives.zip_access',
}


class _AliasLoader(Loader):
    def __init__(self, target):
        self.target = target

    def create_module(self, spec):
        module = import_module(self.target)
        self.canonical_spec = module.__spec__
        return module

    def exec_module(self, module):
        # importlib assigns the alias spec to the returned module. Restore its
        # canonical spec so reload, relative imports and introspection stay valid.
        module.__spec__ = self.canonical_spec


class _AliasFinder(MetaPathFinder):
    def __init__(self, package):
        self.prefix = package + '.'

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.prefix):
            return None
        relative = fullname[len(self.prefix):]
        head, separator, tail = relative.partition('.')
        canonical = ALIASES.get(head)
        if canonical is None:
            return None
        target_name = self.prefix + canonical + (separator + tail if separator else '')
        return spec_from_loader(fullname, _AliasLoader(target_name))


def install(package):
    prefix = package + '.'
    if not any(isinstance(finder, _AliasFinder) and finder.prefix == prefix
               for finder in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder(package))


def legacy_attribute(package, name):
    if name not in ALIASES:
        raise AttributeError(f'module {package!r} has no attribute {name!r}')
    return import_module(package + '.' + name)
