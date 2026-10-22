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

    def test_filtered_rewrite_uses_the_same_plan_and_preserves_member_metadata(self):
        from zipfile import ZipInfo
        from commonUtils.archives.rebuilding import member_plan
        source, target = BytesIO(), BytesIO()
        with ZipFile(source, 'w') as original:
            info = ZipInfo('é😀.txt', (2020, 1, 2, 3, 4, 6))
            info.comment, info.external_attr = b'entry comment', 0o100755 << 16
            original.writestr(info, b'before')
            original.writestr('removed', b'not copied')
        source.seek(0)
        with ZipFile(source) as original, ZipFile(target, 'w') as output:
            output.comment = b'caller-owned'
            plan = tuple(member_plan(original, {'é😀.txt': b'after', 'added': b'new'}, include={'é😀.txt'}))
            self.assertEqual([item.name for item in plan], ['é😀.txt', 'added'])
            expected = rewrite_members(original, output, {'é😀.txt': b'after', 'added': b'new'},
                                       include={'é😀.txt'}, preserve_comment=False)
        target.seek(0)
        with ZipFile(target) as result:
            self.assertEqual(content_manifest(result), expected)
            self.assertEqual(result.comment, b'caller-owned')
            info = result.getinfo('é😀.txt')
            self.assertEqual(info.comment, b'entry comment')
            self.assertEqual(info.external_attr, 0o100755 << 16)
            self.assertEqual(info.date_time, (2020, 1, 2, 3, 4, 6))
