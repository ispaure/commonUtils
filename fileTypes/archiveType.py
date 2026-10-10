"""Passive archive inspection hooks shared by ZIP and TAR file objects."""
from ..fileUtils import File
from ..filesystem import BrowserDetails, BrowserPanel, format_size
from ..archives import TAR_SUFFIXES


class ArchiveFile(File):
    def archive_entries(self):
        from ..archives import entries
        return entries(self.path)

    def extract_to_new_directory(self, destination, **options):
        from ..archives import extract
        return extract(self.path, destination, **options)

    def browser_panels(self):
        return (BrowserPanel('archive.contents', 'Archive Contents', self._archive_details),)

    def _archive_details(self):
        entries = self.archive_entries()
        files = [entry for entry in entries if not entry.directory]
        fields = (('Files', f'{len(files):,}'),
                  ('Directories', f'{sum(entry.directory for entry in entries):,}'),
                  ('Unpacked size', format_size(sum(entry.size for entry in files), binary_units=True)),
                  ('Protection', 'Encrypted file contents' if any(entry.encrypted for entry in entries) else 'None'))
        listing = '\n'.join(entry.name for entry in entries[:40])
        if len(entries) > 40:
            listing += f'\n… {len(entries) - 40:,} more entries'
        return BrowserDetails(fields=fields, message=listing or 'This archive is empty.')


from .registry import register_file_type
register_file_type(ArchiveFile, tuple(suffix.lstrip('.') for suffix in TAR_SUFFIXES), priority=-100)
