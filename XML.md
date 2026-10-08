# XML documents

`fileTypes.xmlType.XMLFile` uses a DOM for structured edits while retaining the
inherited TXT line operations. The DOM and `line_lst` are independent: editing one
does not update the other. The existing direct-field methods remain suited to
formats such as ComicInfo; the explicit-element methods handle nested/repeated data.

## Load and preserve a document

```python
from commonUtils.fileTypes.xmlType import XMLFile

original = b'<Root><!--keep--><Title>Old</Title></Root>'
document = XMLFile.from_bytes(original)
assert document.to_bytes() == original

document.set_text('Title', 'New & <title>')
updated = document.to_bytes()  # Validates and returns bytes; no disk write.
```

For a file, use `XMLFile(path).read_xml()`, which returns `xml_root`. The root loads
lazily when a structured method first needs it. `from_bytes()` honors the XML input
encoding, including BOMs; unchanged output returns the exact input bytes. Edited
output is UTF-8 and may change formatting, entity spelling or CDATA representation.
Comments, processing instructions, unknown elements/attributes and namespace
declarations and an explicit `standalone` declaration survive unrelated edits.
DTD declarations are retained, but this is
not a schema validator or external-entity resolver.

## Choose simple fields or explicit elements

| Method | Behavior |
| --- | --- |
| `get_text(name)` | Direct child in the root namespace; missing means empty text |
| `set_text(name, value)` | Direct child; empty text removes it |
| `find_elements(path, ...)` | Tuple of matching DOM elements, in document order |
| `find_element(path, ...)` | One element or None; multiple matches raise ValueError |
| `get_element_text(element)` | Text/CDATA of an explicit leaf, preserving whitespace |
| `set_element_text(element, value)` | Updates a leaf; empty text keeps the element |
| `get_attribute(element, name, default=None, ...)` | Attribute string, or the supplied default if absent |
| `set_attribute(element, name, value, ...)` | String sets; empty string keeps; None removes |
| `add_element(name, parent=None, text=None, ...)` | Appends and returns a new DOM element |
| `remove_element(element)` | Removes the element/subtree; refuses the document root |
| `write_xml(path=None)` | Atomically writes the DOM after successful serialization |

Simple fields must be unique and contain no child elements. Explicit text methods
also refuse mixed content rather than discarding embedded elements. Comments and
processing instructions inside an edited leaf are retained; text/CDATA becomes a
single text value. For deliberate mixed-content changes, edit the DOM directly.
Nodes passed to helpers must be attached to this document's root.

## Nested and repeated elements

```python
from commonUtils.fileTypes.xmlType import XMLFile

document = XMLFile.from_bytes(b'<Catalog><Books><Book id="1"><Title>Old</Title></Book>'
                              b'<Book id="2"><Title>Other</Title></Book></Books></Catalog>')
books = document.find_elements('Books/Book')
for book in books:
    title = document.find_element('Title', parent=book)
    print(document.get_attribute(book, 'id'), document.get_element_text(title))

document.set_element_text(document.find_element('Title', parent=books[0]), 'New')
new_book = document.add_element('Book', parent=document.find_element('Books'))
document.set_attribute(new_book, 'id', '3')
document.add_element('Title', parent=new_book, text='Third')
document.remove_element(books[1])
```

Paths are a small **relative child-path** language: `Books/Book`, `./Books/Book`,
`.` and `*` steps. They are not full XPath. Absolute paths, parent/descendant axes
and predicates such as `Book[1]` are unsupported. Use the returned tuple to index
repeated elements explicitly. `find_element` rejects multiple matches so edits
cannot silently select the wrong record.

## Namespaces and attributes

```python
from commonUtils.fileTypes.xmlType import XMLFile

document = XMLFile.from_bytes(b'<Catalog xmlns="urn:catalog" xmlns:x="urn:extra">'
                              b'<Book id="1" x:rating="good"/></Catalog>')
book = document.find_element('Book')  # Bare elements match the parent's namespace.
assert document.get_attribute(book, 'id') == '1'  # Bare attributes have no namespace.
assert document.get_attribute(book, 'x:rating') == 'good'
assert document.get_attribute(book, '{urn:extra}rating') == 'good'

document.set_attribute(book, 'review:status', 'read', namespaces={'review': 'urn:review'})
document.add_element('{urn:extra}Note', parent=book, text='Example')
document.add_element('{}Local', parent=book, text='No namespace')
```

Names support local names, `prefix:Name` and Clark notation `{URI}Name`. Prefixes
resolve from the element's in-scope declarations, with optional `namespaces` aliases.
Clark namespace URIs may contain slashes. Bare element names use each parent's
namespace; `{}` explicitly selects no namespace. Bare attributes always have no
namespace, even when the element has a default namespace.

Creation reuses an existing namespace binding or declares one, generating `ns1`,
`ns2`, etc. when a prefix is needed. An unnamespaced child beneath a default namespace
gets `xmlns=""`. Setting an attribute refuses rebinding an existing prefix because
that could change existing element/attribute meanings. Use another alias or Clark
notation instead. The `xml` namespace is fixed; namespace-declaration attributes
are managed by these helpers rather than edited through `set_attribute`.

Attribute tabs, newlines and carriage returns are serialized as character
references, including for direct DOM edits. This prevents an XML reader from
normalizing their values into spaces. Ordinary text preserves carriage returns
through character references as well.

## Save atomically

```python
from commonUtils.fileTypes.xmlType import XMLFile

# An in-memory document uses a synthetic path; supply an explicit export path.
document = XMLFile.from_bytes(b'<Root><Title>Example</Title></Root>')
document.write_xml('output/document.xml')

# For an existing file, write_xml() saves to that object's path.
loaded = XMLFile('output/document.xml')
loaded.set_text('Title', 'Updated')
loaded.write_xml()
```

Serialization/validation happens before touching the destination. The writer
creates parent directories, stages beside the target, flushes it, preserves an
existing file's ordinary mode bits, and replaces it atomically. New files use the
temporary file's private mode. Failed serialization, staging or replacement leaves
an existing destination intact and cleans temporary output. Symlink destinations
are refused. An alternate export path leaves the object's path and size unchanged;
saving its own path refreshes size. The writer does not serialize `line_lst`.

This is a per-file atomic replacement, without source-change detection or a
multi-file transaction. Applications rewriting archives should keep their own
staging, concurrent-change checks and archive verification. Comics continues using
its existing verified CBZ replacement workflow, not this file writer.

## Compatibility

Existing `from_bytes`, `read_xml`, `xml_root`, `get_text`, `set_text` and `to_bytes`
names/signatures remain unchanged. Invalid XML names and values raise errors;
unsupported/ambiguous queries are not silently accepted. Direct DOM changes remain
visible to `to_bytes()`, even when they bypass the helper methods. See
[file types](fileTypes/README.md) for inherited operations and
[workflow recipes](RECIPES.md) for related examples.
