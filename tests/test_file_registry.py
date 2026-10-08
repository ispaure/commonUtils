"""Global registration, priority, built-ins and Directory listing compatibility."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.dirUtils import Directory
from commonUtils.fileUtils import File
from commonUtils.fileTypes.registry import (FileTypeRegistry, file_from_path,
    register_file_type, override_file_type, file_types, object_from_path)


class ProjectFile(File):
    pass


from commonUtils.fileTypes.txtType import TXTFile
from commonUtils.fileTypes.markdownType import MarkdownFile
from commonUtils.features import Feature, FileType, FileTypeOverride


class CustomText(TXTFile):
    pass


class FurtherCustomText(CustomText):
    pass


class OtherCustomText(TXTFile):
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

    def test_owner_toggles_preserve_fallback_priority_and_scoped_registration(self):
        registry = FileTypeRegistry()
        base = registry.register(File, 'owned')
        with registry.owner_scope('feature'):
            custom = registry.register(ProjectFile, 'owned', priority=10)
        self.assertEqual(custom.owner, 'feature')
        self.assertIs(registry.resolve('file.owned'), ProjectFile)
        revision = registry.revision
        registry.set_owner_enabled('feature', False)
        self.assertGreater(registry.revision, revision)
        self.assertIs(registry.resolve('file.owned'), File)
        self.assertEqual(registry.register(ProjectFile, 'owned', priority=10, owner='feature'), custom)
        self.assertIs(registry.resolve('file.owned'), File)
        registry.set_owner_enabled('feature', True)
        self.assertIs(registry.resolve('file.owned'), ProjectFile)
        self.assertIsNone(base.owner)

    def test_owner_scope_restores_after_exception(self):
        registry = FileTypeRegistry()
        with self.assertRaises(ValueError):
            with registry.owner_scope('feature'):
                raise ValueError('failed hook')
        self.assertIsNone(registry.register(File, 'other').owner)

    def test_subclass_override_separate_from_extensions_and_keeps_specializations(self):
        registry = FileTypeRegistry()
        registry.register(TXTFile, ('txt', 'text'))
        registry.register(MarkdownFile, 'md')
        registration = registry.register_override(TXTFile, CustomText)
        self.assertIs(registry.resolve('note.TXT'), CustomText)
        self.assertIs(registry.resolve('note.text'), CustomText)
        self.assertIs(registry.resolve('note.md'), MarkdownFile)
        self.assertIs(registry.resolve('unknown.bin'), File)
        self.assertEqual(registry.register_override(TXTFile, CustomText), registration)
        registry.unregister(registration)
        self.assertIs(registry.resolve('note.txt'), TXTFile)

    def test_override_validation_priority_chains_and_owner_toggles(self):
        registry = FileTypeRegistry()
        registry.register(TXTFile, 'txt')
        with registry.owner_scope('text_plugin'):
            first = registry.register_override(TXTFile, CustomText, priority=10)
            chain = registry.register_override(CustomText, FurtherCustomText)
        second = registry.register_override(TXTFile, OtherCustomText)
        self.assertIs(registry.resolve('note.txt'), FurtherCustomText)
        revision = registry.revision
        registry.set_owner_enabled('text_plugin', False)
        self.assertGreater(registry.revision, revision)
        self.assertIs(registry.resolve('note.txt'), OtherCustomText)
        self.assertEqual(registry.register_override(TXTFile, CustomText, priority=10, owner='text_plugin'), first)
        self.assertIs(registry.resolve('note.txt'), OtherCustomText)
        registry.set_owner_enabled('text_plugin', True)
        registry.unregister(chain)
        self.assertIs(registry.resolve('note.txt'), CustomText)
        registry.unregister(first)
        self.assertIs(registry.resolve('note.txt'), OtherCustomText)
        registry.unregister(second)
        for base, replacement in ((TXTFile, File), (TXTFile, ProjectFile), (TXTFile, TXTFile),
                                  (object, CustomText), (TXTFile, 'invalid')):
            with self.subTest(base=base, replacement=replacement), self.assertRaises(TypeError):
                registry.register_override(base, replacement)

    def test_latest_override_wins_ties_and_generic_file_fallback_can_be_replaced(self):
        registry = FileTypeRegistry()
        registry.register(TXTFile, 'txt')
        registry.register_override(TXTFile, CustomText)
        latest = registry.register_override(TXTFile, OtherCustomText)
        self.assertIs(registry.resolve('note.txt'), OtherCustomText)
        registry.register_override(File, ProjectFile)
        self.assertIs(registry.resolve('unknown'), ProjectFile)
        self.assertIs(registry.resolve('note.txt'), OtherCustomText)
        registry.unregister(latest)
        self.assertIs(registry.resolve('note.txt'), CustomText)

    def test_global_override_existing_directory_inheritance_and_direct_constructors(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'note.txt'
            path.write_text('Original line\n', encoding='utf-8')
            directory = Directory(path.parent)
            original = file_from_path(path)
            registration = override_file_type(TXTFile, CustomText)
            self.addCleanup(file_types.unregister, registration)
            resolved = directory.list_files()[0]
            self.assertIs(type(resolved), CustomText)
            resolved.read_lines()
            self.assertEqual(resolved.line_lst, ['Original line'])
            self.assertIs(type(original), TXTFile)
            self.assertIs(type(TXTFile(path)), TXTFile)
            self.assertIs(type(file_from_path('missing.md')), MarkdownFile)
            self.assertEqual(type(file_from_path('missing.json')).__name__, 'JSONFile')

    def test_feature_override_declaration_lazy_references_and_fallback(self):
        feature = Feature(id='override_test', file_type_overrides=[
            FileTypeOverride('commonUtils.fileTypes.txtType:TXTFile', f'{__name__}:CustomText')])
        handles = feature.register_types()
        for handle in handles:
            self.addCleanup(file_types.unregister, handle)
        self.assertEqual(feature.register_types(), handles)
        self.assertIs(type(file_from_path('missing.txt')), CustomText)
        feature.set_enabled(False)
        self.assertIs(type(file_from_path('missing.txt')), TXTFile)
        feature.set_enabled(True)
        self.assertIs(type(file_from_path('missing.txt')), CustomText)
        self.assertEqual(handles[0].owner, feature.id)
        for args in ((TXTFile, ProjectFile), (object, CustomText), (TXTFile, TXTFile)):
            with self.assertRaises(TypeError):
                FileTypeOverride(*args)
        with self.assertRaises(TypeError):
            Feature(id='bad_override', file_type_overrides=[FileType(CustomText, 'txt')])

    def test_invalid_lazy_override_does_not_install_feature_extension_rules(self):
        feature = Feature(id='invalid_override', file_types=[FileType(ProjectFile, 'mustnotregister')],
                          file_type_overrides=[FileTypeOverride('commonUtils.fileTypes.txtType:TXTFile',
                                                               f'{__name__}:ProjectFile')])
        with self.assertRaises(TypeError):
            feature.register_types()
        self.assertIs(type(file_from_path('missing.mustnotregister')), File)
