"""Member replacement preserves unrelated content, attributes, order and comments."""
from io import BytesIO
import unittest
from zipfile import ZipFile, ZIP_STORED
from commonUtils.archives.rebuilding import content_manifest, patched_manifest, rewrite_members
from commonUtils.runtime.operations import OperationCancelled


class ArchiveRebuildingTests(unittest.TestCase):
    def source(self):
        data = BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.comment = b'kept'
            archive.writestr('untouched', b'payload')
            archive.writestr('metadata', b'before')
            archive.writestr('first', b'kind')
            archive.writestr('empty/', b'')
        data.seek(0)
        return data

    def test_replacements_additions_and_container_options(self):
        target = BytesIO()
        with ZipFile(self.source()) as original, ZipFile(target, 'w') as output:
            replacements = {'metadata': b'after', 'added': b'new'}
            expected = patched_manifest(original, replacements)
            self.assertEqual(rewrite_members(original, output, replacements, first=('first',), stored=('first',)), expected)
        target.seek(0)
        with ZipFile(target) as result:
            self.assertEqual(result.comment, b'kept')
            self.assertEqual(result.namelist()[0], 'first')
            self.assertEqual(result.getinfo('first').compress_type, ZIP_STORED)
            self.assertEqual(result.read('untouched'), b'payload')
            self.assertEqual(content_manifest(result), expected)

    def test_cancellation_and_member_bounds(self):
        with ZipFile(self.source()) as original, ZipFile(BytesIO(), 'w') as output:
            with self.assertRaises(OperationCancelled): rewrite_members(original, output, {}, cancelled=lambda: True)
            with self.assertRaises(ValueError): rewrite_members(original, output, {}, max_member_bytes=1)
