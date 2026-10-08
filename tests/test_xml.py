"""Generic DOM XML workflows and lossless legacy field compatibility."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import stat
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from commonUtils.fileTypes.xmlType import XMLFile


class XMLTests(unittest.TestCase):
    def test_queries_nested_repeated_and_namespaced_elements(self):
        document = XMLFile.from_bytes(b'<Root xmlns="urn:root" xmlns:x="https://example.com/ns">'
                                      b'<Group><Item id="1"/><Item id="2"/><x:Item id="3"/></Group></Root>')
        elements = document.find_elements('Group/Item')
        self.assertEqual([document.get_attribute(item, 'id') for item in elements], ['1', '2'])
        self.assertEqual(len(document.find_elements('./Group/*')), 3)
        self.assertEqual(document.find_elements('.'), (document.xml_root,))
        self.assertIsNone(document.find_element('Missing'))
        with self.assertRaises(ValueError):
            document.find_element('Group/Item')
        extension = document.find_element('Group/{https://example.com/ns}Item')
        self.assertEqual(document.get_attribute(extension, 'id'), '3')
        self.assertIs(extension, document.find_element('Group/extra:Item', namespaces={'extra':'https://example.com/ns'}))
        for path in ('/Group', 'Group//Item', 'Group/Item[1]', '../Group', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                document.find_elements(path)
        with self.assertRaises(ValueError):
            document.find_elements('unknown:Item')

    def test_element_text_keeps_empty_element_and_rejects_mixed_content(self):
        data = b'<Root><Text a="1">A<![CDATA[B]]><!--keep--><?inside yes?>C</Text><Mixed>A<Child/>B</Mixed></Root>'
        document = XMLFile.from_bytes(data)
        element = document.find_element('Text')
        self.assertEqual(document.get_element_text(element), 'ABC')
        document.set_element_text(element, 'ABC')
        self.assertEqual(document.to_bytes(), data)
        document.set_element_text(element, '')
        self.assertIs(document.find_element('Text'), element)
        self.assertEqual(document.get_element_text(element), '')
        self.assertIn(b'<!--keep-->', document.to_bytes())
        self.assertIn(b'<?inside yes?>', document.to_bytes())
        document.set_element_text(element, 'A & <B>\r\u2028C')
        self.assertEqual(ET.fromstring(document.to_bytes()).findtext('Text'), 'A & <B>\r\u2028C')
        before = document.to_bytes()
        with self.assertRaises(ValueError):
            document.set_element_text(document.find_element('Mixed'), 'replace children')
        with self.assertRaises(ET.ParseError):
            document.set_element_text(element, '\x00')
        self.assertEqual(document.to_bytes(), before)

    def test_namespaced_creation_attributes_and_no_namespace_children(self):
        document = XMLFile.from_bytes(b'<r:Root xmlns:r="urn:root" xmlns="urn:default"/>')
        inherited = document.add_element('Child', text='one')
        self.assertEqual(inherited.namespaceURI, 'urn:root')
        plain = document.add_element('{}Plain', text='')
        extension = document.add_element('x:Extra', namespaces={'x':'urn:extra'})
        document.set_attribute(extension, 'x:kind', 'new')
        document.set_attribute(extension, '{urn:other}flag', 'yes')
        document.set_attribute(extension, 'xml:lang', 'fr')
        document.set_attribute(extension, 'empty', '')
        self.assertEqual(document.get_attribute(extension, 'empty', default='missing'), '')
        self.assertIsNone(document.get_attribute(extension, 'absent'))
        self.assertEqual(document.get_attribute(extension, '{urn:other}flag'), 'yes')
        document.set_attribute(extension, 'empty', None)
        parsed = ET.fromstring(document.to_bytes())
        self.assertEqual(parsed.findtext('{urn:root}Child'), 'one')
        self.assertIsNotNone(parsed.find('Plain'))
        self.assertEqual(parsed.find('{urn:extra}Extra').get('{urn:other}flag'), 'yes')
        self.assertEqual(parsed.find('{urn:extra}Extra').get('{http://www.w3.org/XML/1998/namespace}lang'), 'fr')
        self.assertNotIn('empty', parsed.find('{urn:extra}Extra').attrib)
        before = document.to_bytes()
        with self.assertRaises(ValueError):
            document.set_attribute(extension, 'x:flag', 'bad', namespaces={'x':'urn:wrong'})
        self.assertEqual(document.to_bytes(), before)
        document.remove_element(plain)
        self.assertIsNone(document.find_element('{}Plain'))
        with self.assertRaises(ValueError):
            document.remove_element(document.xml_root)
        with self.assertRaises(ValueError):
            document.get_element_text(plain)

    def test_foreign_nodes_invalid_names_and_values_do_not_mutate_document(self):
        document = XMLFile.from_bytes(b'<Root><Title>Old</Title></Root>')
        foreign = XMLFile.from_bytes(b'<Other/>').xml_root
        before = document.to_bytes()
        for name in ('Title injected="yes"', 'Title/><Other', 'Title:bad'):
            with self.subTest(name=name), self.assertRaises((ValueError, ET.ParseError)):
                document.set_text(name, 'bad')
        with self.assertRaises(ValueError):
            document.add_element('Child', parent=foreign)
        with self.assertRaises(ET.ParseError):
            document.add_element('Child', text='\x00')
        with self.assertRaises(TypeError):
            document.set_attribute(document.xml_root, 'count', 12)
        with self.assertRaises(ValueError):
            document.set_attribute(document.xml_root, 'xmlns', 'urn:bad')
        self.assertEqual(document.to_bytes(), before)

    def test_attribute_whitespace_preserved_after_unrelated_and_direct_dom_edits(self):
        data = b'<?xml version="1.0"?><!--before--><Root a="A&#9;B&#10;C&#13;D &amp; &quot; E"><Title>Old</Title></Root><?after yes?>'
        document = XMLFile.from_bytes(data)
        self.assertEqual(document.to_bytes(), data)
        document.set_text('Title', 'New')
        expected = 'A\tB\nC\rD & " E'
        self.assertEqual(ET.fromstring(document.to_bytes()).get('a'), expected)
        self.assertEqual(document.xml_root.getAttribute('a'), expected)
        document.xml_root.setAttribute('direct', 'one\ntwo\tthree\rfour')
        document.set_attribute(document.xml_root, 'helper', '\t\n\r')
        parsed = ET.fromstring(document.to_bytes())
        self.assertEqual(parsed.get('direct'), 'one\ntwo\tthree\rfour')
        self.assertEqual(parsed.get('helper'), '\t\n\r')
        self.assertIn(b'<!--before-->', document.to_bytes())
        self.assertIn(b'<?after yes?>', document.to_bytes())

    def test_input_encodings_bom_internal_entities_and_noop_bytes(self):
        for encoding in ('utf-8', 'utf-16', 'iso-8859-1'):
            text = f'<?xml version="1.0" encoding="{encoding}"?><Root><Title>Été</Title></Root>'
            data = text.encode(encoding)
            with self.subTest(encoding=encoding):
                document = XMLFile.from_bytes(data)
                self.assertEqual(document.to_bytes(), data)
                document.set_text('Title', 'Updated été')
                self.assertEqual(ET.fromstring(document.to_bytes()).findtext('Title'), 'Updated été')
        data = b'<!DOCTYPE Root [<!ENTITY greeting "hello">]><Root spaces="a&#9;b"><Title>&greeting;</Title></Root>'
        document = XMLFile.from_bytes(data)
        self.assertEqual(document.get_text('Title'), 'hello')
        self.assertEqual(document.to_bytes(), data)
        document.set_text('Added', 'new')
        self.assertIn(b'<!DOCTYPE Root', document.to_bytes())
        self.assertEqual(ET.fromstring(document.to_bytes()).findtext('Title'), 'hello')

    def test_serialization_tokens_cannot_replace_real_content(self):
        data = b'<Root marker="__commonUtilsXMLAttribute__0__" whitespace="a&#10;b">__commonUtilsXMLAttribute__1__</Root>'
        document = XMLFile.from_bytes(data)
        document.set_attribute(document.xml_root, 'added', 'yes')
        parsed = ET.fromstring(document.to_bytes())
        self.assertEqual(parsed.get('marker'), '__commonUtilsXMLAttribute__0__')
        self.assertEqual(parsed.get('whitespace'), 'a\nb')
        self.assertEqual(parsed.text, '__commonUtilsXMLAttribute__1__')

    def test_external_entities_and_reserved_namespace_aliases_are_rejected(self):
        with self.assertRaises(ET.ParseError):
            XMLFile.from_bytes(b'<!DOCTYPE Root [<!ENTITY external SYSTEM "file:///not-read">]>'
                               b'<Root>&external;</Root>')
        document = XMLFile.from_bytes(b'<Root/>')
        before = document.to_bytes()
        for name, namespaces in (('xml:lang', {'xml':'urn:wrong'}),
                                 ('alias:lang', {'alias':'http://www.w3.org/XML/1998/namespace'})):
            with self.subTest(name=name), self.assertRaises(ValueError):
                document.set_attribute(document.xml_root, name, 'bad', namespaces=namespaces)
        self.assertEqual(document.to_bytes(), before)

    def test_standalone_declaration_survives_edits_and_attribute_cloning(self):
        for standalone in ('yes', 'no'):
            with self.subTest(standalone=standalone):
                data = (f'<?xml version="1.0" standalone="{standalone}"?>'
                        '<Root a="one&#10;two"><Title>Old</Title></Root>').encode()
                document = XMLFile.from_bytes(data)
                self.assertEqual(document.to_bytes(), data)
                document.set_text('Title', 'New')
                self.assertIn(f'standalone="{standalone}"'.encode(), document.to_bytes())
                self.assertEqual(ET.fromstring(document.to_bytes()).get('a'), 'one\ntwo')

    def test_legacy_simple_field_contract_and_line_list_remain_separate(self):
        document = XMLFile.from_bytes(b'<Root><Title>Old</Title><Item/><Item/><Nested><Child/></Nested></Root>')
        document.line_lst = ['untouched']
        with self.assertRaises(ValueError):
            document.get_text('Item')
        with self.assertRaises(ValueError):
            document.set_text('Nested', 'new')
        document.set_text('Title', '')
        self.assertIsNone(document.find_element('Title'))
        self.assertEqual(document.get_text('Missing'), '')
        self.assertEqual(document.line_lst, ['untouched'])

    def test_string_paths_lazy_loading_and_failed_reload_keep_current_document(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'record.xml'
            path.write_bytes(b'<Root><Title>Original</Title></Root>')
            document = XMLFile(str(path))
            self.assertEqual(document.get_text('Title'), 'Original')
            document.set_text('Title', 'Updated')
            document.write_xml()
            self.assertEqual(ET.fromstring(path.read_bytes()).findtext('Title'), 'Updated')
            path.write_bytes(b'<invalid>')
            with self.assertRaises(ET.ParseError):
                document.read_xml()
            self.assertEqual(document.get_text('Title'), 'Updated')

    def test_atomic_writer_failure_export_and_permissions(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'record.xml'
            path.write_bytes(b'<Root><Title>Old</Title></Root>')
            if os.name != 'nt':
                path.chmod(0o640)
            original = path.read_bytes()
            original_mode = stat.S_IMODE(path.stat().st_mode)
            document = XMLFile(path)
            document.read_xml()
            document.set_text('Title', 'New')
            with patch('commonUtils.fileTypes.xmlType.os.replace', side_effect=OSError('replace failed')):
                with self.assertRaises(OSError):
                    document.write_xml()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.glob('.record.xml-*.tmp')), [])
            exported = path.parent/'nested'/'export.xml'
            old_size = document.size
            document.write_xml(exported)
            self.assertEqual(document.path, path)
            self.assertEqual(document.size, old_size)
            self.assertEqual(path.read_bytes(), original)
            document.write_xml()
            self.assertEqual(path.read_bytes(), exported.read_bytes())
            self.assertEqual(document.size, path.stat().st_size)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), original_mode)
            document.xml_root.setAttribute('bad', '\x00')
            before = path.read_bytes()
            with self.assertRaises(ET.ParseError):
                document.write_xml()
            self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(os.name == 'posix', 'Symlink fixture requires POSIX')
    def test_writer_refuses_symlink_destination(self):
        with TemporaryDirectory() as temporary:
            target=Path(temporary)/'target.xml'; target.write_bytes(b'<Original/>')
            link=Path(temporary)/'link.xml'; link.symlink_to(target)
            document=XMLFile.from_bytes(b'<Root/>')
            with self.assertRaises(ValueError):
                document.write_xml(link)
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_bytes(), b'<Original/>')
