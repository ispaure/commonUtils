"""Whole XML documents preserve extensions, outer nodes and direct DOM edits."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET


class XMLDocumentPreservationTests(unittest.TestCase):
    def test_full_document_and_namespace_extensions_are_preserved(self):
        from commonUtils.formats.xmlType import XMLFile
        data = (b'<?xml version="1.0"?><!--before--><?before yes?>'
                b'<c:Record xmlns:c="urn:root" xmlns:x="urn:extra" xmlns:unused="urn:unused" '
                b'x:kind="unused:Type"><c:Title keep="yes">Old</c:Title>'
                b'<x:Title>Extension title</x:Title><x:Data a="b"><x:Child/>Tail</x:Data>'
                b'<!--inside--></c:Record><?after yes?><!--after-->')
        document = XMLFile.from_bytes(data)
        self.assertEqual(document.to_bytes(), data)
        document.set_text('Title', 'New & <title>')
        document.set_text('Added', 'New')
        result = document.to_bytes()
        root = ET.fromstring(result)
        self.assertEqual(root.findtext('{urn:root}Title'), 'New & <title>')
        self.assertEqual(root.find('{urn:root}Title').get('keep'), 'yes')
        self.assertEqual(root.findtext('{urn:extra}Title'), 'Extension title')
        self.assertEqual(root.findtext('{urn:root}Added'), 'New')
        self.assertEqual(root.find('{urn:extra}Data').get('a'), 'b')
        self.assertEqual(root.find('{urn:extra}Data/{urn:extra}Child').tail, 'Tail')
        for preserved in (b'<!--before-->', b'<?before yes?>', b'<!--inside-->',
                          b'<?after yes?>', b'<!--after-->', b'xmlns:unused="urn:unused"'):
            self.assertIn(preserved, result)

    def test_generic_file_loading_is_separate_from_lines(self):
        from commonUtils.formats.xmlType import XMLFile
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'record.xml'
            path.write_text('<Record><Title>Old</Title></Record>')
            document = XMLFile(path)
            document.line_lst = ['untouched']
            self.assertEqual(document.read_xml().localName, 'Record')
            document.set_text('Title', 'New')
            self.assertEqual(document.line_lst, ['untouched'])
            self.assertEqual(document.get_text('Title'), 'New')
            self.assertEqual(path.read_text(), '<Record><Title>Old</Title></Record>')

    def test_direct_dom_changes_are_serialized(self):
        from commonUtils.formats.xmlType import XMLFile
        document = XMLFile.from_bytes(b'<Root><Item>Old</Item></Root>')
        document.xml_root.setAttribute('added', 'yes')
        self.assertEqual(ET.fromstring(document.to_bytes()).get('added'), 'yes')
