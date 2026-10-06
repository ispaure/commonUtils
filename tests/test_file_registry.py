"""Global registration, priority, built-ins and Directory listing compatibility."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.dirUtils import Directory
from commonUtils.fileUtils import File
from commonUtils.fileTypes.registry import (FileTypeRegistry, file_from_path,
    register_file_type, file_types, object_from_path)


class ProjectFile(File):
    pass


class RegistryTests(unittest.TestCase):
    def test_existing_directories_see_later_global_registration(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'a.project').touch()
            (root / 'nested').mkdir()
            (root / 'nested' / 'b.PROJECT').touch()
            directory = Directory(root)
            self.assertIs(type(directory.list_files()[0]), File)
            registration = register_file_type(ProjectFile, '.project')
            self.addCleanup(file_types.unregister, registration)
            self.assertTrue(all(isinstance(item, ProjectFile) for item in directory.list_files()))
            self.assertIsInstance(Directory(root).list_files(recursive=False)[0], ProjectFile)
            self.assertEqual(len(directory.list_files(filter_extension='.PROJECT')), 2)
            self.assertIsInstance(object_from_path(root), Directory)
            self.assertIsInstance(file_from_path(root / 'a.project'), ProjectFile)

    def test_builtins_resolve_without_reading_content(self):
        for extension, class_name in [('txt', 'TXTFile'), ('csv', 'CSVFile'), ('json', 'JSONFile'),
                                      ('xml', 'XMLFile'), ('zip', 'ZIPFile'), ('dmg', 'DMGFile'),
                                      ('appimage', 'AppImageFile')]:
            self.assertEqual(type(file_from_path(Path('missing.' + extension.upper()))).__name__, class_name)
        self.assertIs(type(file_from_path('unknown')), File)

    def test_detection_priority_compound_suffixes_and_unregister(self):
        registry = FileTypeRegistry()
        base = registry.register(File, 'zip')
        custom = registry.register(ProjectFile, 'comic.zip', detector=lambda path: path.name.startswith('yes'), priority=10)
        self.assertIs(registry.resolve('yes.comic.zip'), ProjectFile)
        self.assertIs(registry.resolve('no.comic.zip'), File)
        self.assertEqual(registry.register(ProjectFile, 'comic.zip', detector=custom.detector, priority=10), custom)
        registry.unregister(custom)
        self.assertIs(registry.resolve('yes.comic.zip'), File)
        registry.register(ProjectFile, detector=lambda path: path.name == 'special')
        self.assertIs(registry.resolve('special'), ProjectFile)
        registry.register(ProjectFile, 'zip')
        self.assertIs(registry.resolve('regular.zip'), ProjectFile)
        for args in [(object, 'bad'), (File, ''), (File, 'dir/bad')]:
            with self.assertRaises((TypeError, ValueError)):
                registry.register(*args)
