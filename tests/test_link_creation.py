"""Real link creation preserves sources and exclusively allocates destination names."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.filesystem.links.creation import create_link, create_link_in_directory


class LinkCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'Art.txt'; self.file.write_text('original')
        self.folder = self.root / 'Folder'; self.folder.mkdir()
        self.destination = self.root / 'Destination'; self.destination.mkdir()

    def test_symbolic_links_support_files_and_folders(self):
        for source in (self.file, self.folder):
            try:
                link = create_link_in_directory(source, self.destination)
            except PermissionError:
                if os.name == 'nt':
                    self.skipTest('Windows symbolic-link privileges unavailable')
                raise
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), source.resolve())

    def test_hard_link_shares_file_and_rejects_folder(self):
        link = create_link_in_directory(self.file, self.destination, 'hard')
        self.assertTrue(os.path.samefile(link, self.file))
        link.write_text('edited')
        self.assertEqual(self.file.read_text(), 'edited')
        with self.assertRaises(ValueError):
            create_link_in_directory(self.folder, self.destination, 'hard')
        self.assertFalse((self.destination / self.folder.name).exists())

    def test_collisions_allocate_names_without_overwriting_existing_resources(self):
        existing = self.destination / self.file.name; existing.write_text('private')
        first = create_link_in_directory(self.file, self.destination, 'hard')
        second = create_link_in_directory(self.file, self.destination, 'hard')
        self.assertEqual(first.name, 'Art - Link.txt')
        self.assertEqual(second.name, 'Art - Link (2).txt')
        self.assertEqual(existing.read_text(), 'private')
        with self.assertRaises(FileExistsError):
            create_link(self.file, existing)
        self.assertEqual(self.file.read_text(), 'original')

    def test_missing_sources_and_unknown_types_do_not_create_destination(self):
        target = self.destination / 'Missing'
        with self.assertRaises(FileNotFoundError):
            create_link(self.root / 'missing', target)
        with self.assertRaises(ValueError):
            create_link(self.file, target, 'invalid')
        self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junctions')
    def test_windows_junction_opens_folder_and_preserves_source(self):
        link = create_link_in_directory(self.folder, self.destination, 'junction')
        self.assertTrue(link.is_junction())
        (link / 'inside.txt').write_text('shared')
        self.assertEqual((self.folder / 'inside.txt').read_text(), 'shared')
        link.rmdir()
        self.assertTrue(self.folder.is_dir())
