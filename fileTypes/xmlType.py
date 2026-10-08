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
from xml.sax.saxutils import escape
import os
import re
import stat
from tempfile import NamedTemporaryFile

# Common utilities
from .txtType import TXTFile


_XMLNS = 'http://www.w3.org/2000/xmlns/'
_XML = 'http://www.w3.org/XML/1998/namespace'


def _serialize_document(document):
    """Keep attribute whitespace as character references, without mutating the DOM."""
    original = document.toxml(encoding='utf-8', standalone=document.standalone)
    has_whitespace = any(any(character in attribute.value for character in '\t\n\r')
                         for element in document.getElementsByTagName('*')
                         for attribute in element.attributes.values())
    if not has_whitespace:
        return original
    marker = '__commonUtilsXMLAttribute__'
    while marker.encode() in original:
        marker += '_'
    clone = document.cloneNode(True)
    replacements = []
    for element in clone.getElementsByTagName('*'):
        for attribute in element.attributes.values():
            if any(character in attribute.value for character in '\t\n\r'):
                token = f'{marker}{len(replacements)}__'
                value = escape(attribute.value, {'"': '&quot;', '\t': '&#9;', '\n': '&#10;', '\r': '&#13;'})
                replacements.append((token.encode(), value.encode('utf-8')))
                attribute.value = token
    try:
        result = clone.toxml(encoding='utf-8', standalone=document.standalone)
    finally:
        clone.unlink()
    for token, value in replacements:
        result = result.replace(token, value)
    return result


class XMLFile(TXTFile):
    def __init__(self, path: Path):
        super().__init__(Path(path))

    @classmethod
    def from_bytes(cls, data: bytes):
        """Parse a full XML document, retaining extensions, comments and PIs.

        Tree editing is separate from inherited line_lst workflows. No-op output
        returns the original bytes; edited output retains all untouched nodes.
        """
        ElementTree.fromstring(data)
        document = cls(Path('document.xml'))
        document._xml_document = minidom.parseString(data)
        document._xml_initial_serialized = _serialize_document(document._xml_document)
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
        self._validate_local_name(name)
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

    @staticmethod
    def _validate_local_name(name):
        if not isinstance(name, str):
            raise TypeError('XML names must be strings')
        # Parsing supports Unicode XML names; insist on exactly one local name.
        element = ElementTree.fromstring(f'<{name}/>')
        if ':' in name or element.tag != name or element.attrib or len(element):
            raise ValueError('Expected an XML local name, not markup or a qualified name')

    def _element(self, element=None):
        root = self.xml_root
        if element is None:
            return root
        if getattr(element, 'nodeType', None) != Node.ELEMENT_NODE:
            raise TypeError('Expected a DOM element')
        current = element
        while current is not None and current is not root:
            current = current.parentNode
        if current is not root:
            raise ValueError('Element must belong to this document and be attached to its root')
        return element

    @staticmethod
    def _bindings(element):
        bindings = {'xml': _XML}
        while element is not None and element.nodeType == Node.ELEMENT_NODE:
            for attribute in element.attributes.values():
                if attribute.name == 'xmlns':
                    bindings.setdefault('', attribute.value)
                elif attribute.name.startswith('xmlns:'):
                    bindings.setdefault(attribute.name[6:], attribute.value)
            element = element.parentNode
        return bindings

    def _name(self, name, element, namespaces=None, *, attribute=False):
        if not isinstance(name, str):
            raise TypeError('XML names must be strings')
        prefix = None
        if name.startswith('{'):
            namespace, separator, local = name[1:].partition('}')
            if not separator:
                raise ValueError('Expected {namespace}local-name')
        elif ':' in name:
            prefix, local = name.split(':', 1)
            self._validate_local_name(prefix)
            bindings = self._bindings(element)
            bindings.update(namespaces or {})
            if prefix not in bindings or not bindings[prefix]:
                raise ValueError(f'Unknown namespace prefix: {prefix}')
            namespace = bindings[prefix]
        else:
            local = name
            namespace = None if attribute else element.namespaceURI
        self._validate_local_name(local)
        if namespace is not None and not isinstance(namespace, str):
            raise TypeError('Namespace URIs must be strings')
        if namespace == _XMLNS or prefix == 'xmlns' or (attribute and local == 'xmlns' and not namespace):
            raise ValueError('Namespace declarations are managed by element/attribute creation')
        if (prefix == 'xml' and namespace != _XML) or (namespace == _XML and prefix not in (None, 'xml')):
            raise ValueError('The XML namespace must use the xml prefix')
        return namespace or None, local, prefix

    @staticmethod
    def _path_steps(path):
        if not isinstance(path, str):
            raise TypeError('XML paths must be strings')
        if path == '.':
            return ()
        if path.startswith('./'):
            path = path[2:]
        # Slashes inside Clark-notation namespace URIs are part of the name.
        steps = re.findall(r'\{[^}]*\}[^/]*|[^/]+', path)
        if not path or '/'.join(steps) != path or any(step in ('.', '..') or '[' in step or ']' in step for step in steps):
            raise ValueError('Use a relative child path; XPath predicates and descendant axes are unsupported')
        return tuple(steps)

    def find_elements(self, path, *, parent=None, namespaces=None):
        """Return matching DOM elements for a relative child path, preserving order.

        Supports nested/repeated children, *, prefix:Name and {URI}Name.
        Bare names match each parent's namespace. {}Name means no namespace.
        """
        elements = (self._element(parent),)
        for step in self._path_steps(path):
            matches = []
            for element in elements:
                expanded = None if step == '*' else self._name(step, element, namespaces)[:2]
                matches.extend(child for child in element.childNodes
                               if child.nodeType == Node.ELEMENT_NODE
                               and (expanded is None or (child.namespaceURI, child.localName) == expanded))
            elements = tuple(matches)
        return elements

    def find_element(self, path, *, parent=None, namespaces=None):
        """Return one match or None; reject ambiguity instead of choosing silently."""
        elements = self.find_elements(path, parent=parent, namespaces=namespaces)
        if len(elements) > 1:
            raise ValueError(f'{path} matches multiple elements; use find_elements')
        return elements[0] if elements else None

    def get_element_text(self, element):
        """Read text/CDATA from one explicit leaf element, retaining whitespace."""
        element = self._element(element)
        if any(child.nodeType == Node.ELEMENT_NODE for child in element.childNodes):
            raise ValueError('Element contains child elements; mixed content cannot be read as one text field')
        return ''.join(child.data for child in element.childNodes
                       if child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE))

    def set_element_text(self, element, value):
        """Edit an explicit leaf; empty text keeps the element (unlike set_text)."""
        element = self._element(element)
        if not isinstance(value, str):
            raise TypeError('XML text values must be strings')
        ElementTree.fromstring('<Value>' + escape(value) + '</Value>')
        if self.get_element_text(element) == value:
            return
        for child in list(element.childNodes):
            if child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE):
                element.removeChild(child)
        element.appendChild(self._xml_document.createTextNode(value))
        self._xml_dirty = True

    def get_attribute(self, element, name, *, namespaces=None, default=None):
        """Unqualified attributes have no namespace; absent values return default."""
        element = self._element(element)
        namespace, local, _ = self._name(name, element, namespaces, attribute=True)
        return element.getAttributeNS(namespace, local) if element.hasAttributeNS(namespace, local) else default

    def _qualified_name(self, element, namespace, local, prefix, *, attribute=False):
        if namespace is None:
            return local, None
        bindings = self._bindings(element)
        if prefix is None:
            prefix = next((key for key, value in bindings.items()
                           if value == namespace and (key or not attribute)), None)
        if prefix is None:
            prefix = 'ns1'
            while prefix in bindings:
                prefix = 'ns' + str(int(prefix[2:]) + 1)
        qualified = f'{prefix}:{local}' if prefix else local
        declaration = None if bindings.get(prefix) == namespace else (prefix, namespace)
        return qualified, declaration

    @staticmethod
    def _declare_namespace(element, declaration):
        if declaration is not None:
            prefix, namespace = declaration
            element.setAttributeNS(_XMLNS, f'xmlns:{prefix}' if prefix else 'xmlns', namespace)

    def set_attribute(self, element, name, value, *, namespaces=None):
        """Set a string, keep an empty attribute, or remove with None."""
        element = self._element(element)
        namespace, local, prefix = self._name(name, element, namespaces, attribute=True)
        if value is None:
            if element.hasAttributeNS(namespace, local):
                element.removeAttributeNS(namespace, local)
                self._xml_dirty = True
            return
        if not isinstance(value, str):
            raise TypeError('XML attribute values must be strings or None')
        ElementTree.fromstring('<Value attribute="' + escape(value, {'"': '&quot;'}) + '"/>')
        qualified, declaration = self._qualified_name(element, namespace, local, prefix, attribute=True)
        if declaration and prefix in self._bindings(element):
            raise ValueError('Cannot rebind an existing namespace prefix on this element')
        self._declare_namespace(element, declaration)
        element.setAttributeNS(namespace, qualified, value)
        self._xml_dirty = True

    def add_element(self, name, *, parent=None, text=None, namespaces=None):
        """Append one element, declaring its namespace when needed; return its DOM node."""
        parent = self._element(parent)
        namespace, local, prefix = self._name(name, parent, namespaces)
        if text is not None:
            if not isinstance(text, str):
                raise TypeError('XML text values must be strings')
            ElementTree.fromstring('<Value>' + escape(text) + '</Value>')
        qualified, declaration = self._qualified_name(parent, namespace, local, prefix)
        element = self._xml_document.createElementNS(namespace, qualified)
        # A no-namespace child must opt out of an inherited default namespace.
        if namespace is None and self._bindings(parent).get(''):
            declaration = ('', '')
        self._declare_namespace(element, declaration)
        if text is not None:
            element.appendChild(self._xml_document.createTextNode(text))
        parent.appendChild(element)
        self._xml_dirty = True
        return element

    def remove_element(self, element):
        """Remove an attached element and its contents; the document root is protected."""
        element = self._element(element)
        if element is self.xml_root:
            raise ValueError('Cannot remove the document root')
        element.parentNode.removeChild(element)
        self._xml_dirty = True

    def write_xml(self, path=None):
        """Serialize before staging, then replace atomically; preserve existing file mode.

        Exporting to another path leaves this object's path and size unchanged.
        Symlink destinations are refused. This writes the DOM, not line_lst.
        """
        data = self.to_bytes()
        destination = Path(path) if path is not None else self.path
        if destination.is_symlink():
            raise ValueError('Refusing to replace an XML destination symlink')
        try:
            permissions = stat.S_IMODE(destination.stat().st_mode)
        except FileNotFoundError:
            permissions = None
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with NamedTemporaryFile(dir=destination.parent, prefix=f'.{destination.name}-',
                                    suffix='.tmp', delete=False) as output:
                staged = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            if permissions is not None:
                staged.chmod(permissions)
            os.replace(staged, destination)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
        if destination.absolute() == self.path.absolute():
            self.size = len(data)

    def to_bytes(self) -> bytes:
        """Serialize the complete document, validating before callers write it."""
        self.xml_root
        serialized = _serialize_document(self._xml_document)
        if serialized == self._xml_initial_serialized:
            return self._xml_original
        data = serialized.replace(b'\r', b'&#13;')
        ElementTree.fromstring(data)  # Reject illegal XML text before a file is touched.
        return data


from .registry import register_file_type
register_file_type(XMLFile, 'xml', priority=-100)
