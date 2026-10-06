# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from typing import *
from pathlib import Path
from xml.dom import minidom, Node
from xml.etree import ElementTree

# Common utilities
from .txtType import TXTFile


class XMLFile(TXTFile):
    def __init__(self, path: Path):
        super().__init__(path)

    @classmethod
    def from_bytes(cls, data: bytes):
        """Parse a full XML document, retaining extensions, comments and PIs.

        Tree editing is separate from inherited line_lst workflows. No-op output
        returns the original bytes; edited output retains all untouched nodes.
        """
        ElementTree.fromstring(data)
        document = cls(Path('document.xml'))
        document._xml_document = minidom.parseString(data)
        document._xml_initial_serialized = document._xml_document.toxml(encoding='utf-8')
        document._xml_original = data
        document._xml_dirty = False
        return document

    def read_xml(self):
        """Load a DOM without changing line_lst or inherited text-file methods."""
        parsed = self.from_bytes(self.path.read_bytes())
        self._xml_document = parsed._xml_document
        self._xml_initial_serialized = parsed._xml_initial_serialized
        self._xml_original = parsed._xml_original
        self._xml_dirty = False
        return self.xml_root

    @property
    def xml_root(self):
        if not hasattr(self, '_xml_document'):
            self.read_xml()
        return self._xml_document.documentElement

    def _text_element(self, name):
        # Names are local names in the root namespace; extension namespaces
        # with the same local name must not be mistaken for application fields.
        root = self.xml_root
        elements = [node for node in root.childNodes
                    if node.nodeType == Node.ELEMENT_NODE
                    and node.localName == name and node.namespaceURI == root.namespaceURI]
        if len(elements) > 1 or (elements and any(
                child.nodeType == Node.ELEMENT_NODE for child in elements[0].childNodes)):
            raise ValueError(f'{name} must be a single text element')
        return elements[0] if elements else None

    def get_text(self, name: str) -> str:
        """Read a direct text child, returning empty text for an absent field."""
        element = self._text_element(name)
        return ''.join(node.data for node in element.childNodes
                       if node.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE)) if element else ''

    def set_text(self, name: str, value: str):
        """Patch one direct child. Empty text removes it; all other nodes survive."""
        if not isinstance(value, str):
            raise TypeError('XML text values must be strings')
        # Validate XML names before constructing a node.
        ElementTree.fromstring(f'<{name}/>')
        if self.get_text(name) == value:
            return
        root = self.xml_root
        element = self._text_element(name)
        if not value:
            if element is not None:
                root.removeChild(element)
        else:
            if element is None:
                qualified = f'{root.prefix}:{name}' if root.prefix else name
                element = self._xml_document.createElementNS(root.namespaceURI, qualified)
                root.appendChild(element)
            for node in list(element.childNodes):
                if node.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE):
                    element.removeChild(node)
            element.appendChild(self._xml_document.createTextNode(value))
        self._xml_dirty = True

    def to_bytes(self) -> bytes:
        """Serialize the complete document, validating before callers write it."""
        self.xml_root
        serialized = self._xml_document.toxml(encoding='utf-8')
        if serialized == self._xml_initial_serialized:
            return self._xml_original
        data = serialized.replace(b'\r', b'&#13;')
        ElementTree.fromstring(data)  # Reject illegal XML text before a file is touched.
        return data
