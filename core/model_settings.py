"""Parse/write Metadata/model_settings.config.

Real files look like:

    <?xml version="1.0" encoding="UTF-8"?>
    <config>
      <object id="26">
        <metadata key="name" value="R_HORN_1.stl"/>
        <metadata key="extruder" value="3"/>
        <part id="25" subtype="normal_part">
          <metadata key="name" value="R_HORN_1.stl"/>
          <metadata key="matrix" value="..."/>
          <metadata key="source_file" value="..."/>
          <mesh_stat edges_fixed="0" degenerate_facets="0" .../>
        </part>
      </object>
    </config>

The "extruder" metadata value is the logical color-slot index -- this is what
convert/color_mapping.py rewrites. Everything else (matrix, source_file,
mesh_stat, brim_type, enable_support, ...) is provenance/print-modifier data
that just needs to survive round-tripping.

Node is a generic lossless tree (tag + attrib + children) so any element or
attribute this module doesn't explicitly know about -- including ones added
by a future slicer version -- still round-trips instead of being silently
dropped. ObjectView/PartView are thin convenience accessors over that tree,
not a separate copy of the data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'

# Namespace URIs for prefixes real files use without declaring. Taking the
# real URI where it is known keeps the document meaning what its author meant;
# anything else gets a placeholder, which is enough to parse and round-trip.
_KNOWN_NAMESPACE_URIS = {
    "slic3rpe": "http://schemas.slic3r.org/3mf/2017/06",
    "p": "http://schemas.microsoft.com/3dmanufacturing/production/2015/06",
}

_PREFIX_IN_TAG = re.compile(r"<\s*([A-Za-z_][\w.-]*):")
_PREFIX_IN_ATTR = re.compile(r"\s([A-Za-z_][\w.-]*):[\w.-]+\s*=")
_DECLARED_PREFIX = re.compile(r"xmlns:([A-Za-z_][\w.-]*)\s*=")
_ROOT_START_TAG = re.compile(r"<\s*([A-Za-z_][\w.-]*)((?:\s[^<>]*)?)(/?)>")


def declare_unbound_prefixes(xml_text: str) -> str:
    """Declare namespace prefixes the document uses but never declares.

    Snapmaker Orca and PrusaSlicer write embossed-text objects as
    `<slic3rpe:shape .../>` and `<slic3rpe:text .../>` inside
    model_settings.config without ever declaring `xmlns:slic3rpe` on the root.
    That is not well-formed XML, and a strict parser refuses the whole
    document -- "unbound prefix" -- so a project containing a single piece of
    embossed text failed to convert at all. The slicers read their own output
    happily, which is how it ships.

    Rather than giving up or throwing the elements away, the missing
    declarations are added to the root element before parsing, and the
    prefixes registered so serialising puts them back verbatim. The round trip
    therefore gains an `xmlns:` declaration on the root and changes nothing
    else -- the output is the same document, now well-formed.
    """
    used = set(_PREFIX_IN_TAG.findall(xml_text)) | set(_PREFIX_IN_ATTR.findall(xml_text))
    used.discard("xmlns")
    missing = sorted(used - set(_DECLARED_PREFIX.findall(xml_text)))
    if not missing:
        return xml_text

    match = _ROOT_START_TAG.search(xml_text)
    if match is None:
        return xml_text  # nothing that looks like a root element; let the parser report it

    declarations = ""
    for prefix in missing:
        uri = _KNOWN_NAMESPACE_URIS.get(prefix, f"urn:crossprint:undeclared:{prefix}")
        # So serialising writes `slic3rpe:shape` again rather than `ns0:shape`.
        ET.register_namespace(prefix, uri)
        declarations += f' xmlns:{prefix}="{uri}"'

    tag, attrs, self_closing = match.groups()
    replacement = f"<{tag}{attrs}{declarations}{self_closing}>"
    return xml_text[: match.start()] + replacement + xml_text[match.end() :]


@dataclass
class Node:
    tag: str
    attrib: dict[str, str] = field(default_factory=dict)
    children: list[Node] = field(default_factory=list)

    @classmethod
    def from_element(cls, el: ET.Element) -> Node:
        return cls(tag=el.tag, attrib=dict(el.attrib), children=[Node.from_element(c) for c in el])

    def to_element(self) -> ET.Element:
        el = ET.Element(self.tag, self.attrib)
        for child in self.children:
            el.append(child.to_element())
        return el


class _MetadataOwner:
    """Shared get/set helpers for nodes whose children include <metadata key=.. value=../> entries."""

    node: Node

    def _metadata_children(self) -> list[Node]:
        return [c for c in self.node.children if c.tag == "metadata"]

    def get_metadata(self, key: str, default: str | None = None) -> str | None:
        for c in self._metadata_children():
            if c.attrib.get("key") == key:
                return c.attrib.get("value")
        return default

    def set_metadata(self, key: str, value: str) -> None:
        for c in self._metadata_children():
            if c.attrib.get("key") == key:
                c.attrib["value"] = value
                return
        # New keys go after the last existing metadata entry (before <part>/<mesh_stat> children).
        insert_at = len(self.node.children)
        for i, c in enumerate(self.node.children):
            if c.tag != "metadata":
                insert_at = i
                break
        self.node.children.insert(insert_at, Node(tag="metadata", attrib={"key": key, "value": value}))


class PartView(_MetadataOwner):
    def __init__(self, node: Node):
        self.node = node

    @property
    def id(self) -> str:
        return self.node.attrib.get("id", "")

    @property
    def subtype(self) -> str:
        return self.node.attrib.get("subtype", "")

    @property
    def name(self) -> str | None:
        return self.get_metadata("name")


class ObjectView(_MetadataOwner):
    def __init__(self, node: Node):
        self.node = node

    @property
    def id(self) -> str:
        return self.node.attrib.get("id", "")

    @property
    def name(self) -> str | None:
        return self.get_metadata("name")

    @property
    def extruder(self) -> str | None:
        """Logical color-slot index for the whole object, if set at object level."""
        return self.get_metadata("extruder")

    @extruder.setter
    def extruder(self, value: str) -> None:
        self.set_metadata("extruder", str(value))

    @property
    def parts(self) -> list[PartView]:
        return [PartView(c) for c in self.node.children if c.tag == "part"]

    def part_extruders(self) -> dict[str, str | None]:
        """Per-part extruder overrides (parts don't usually carry their own 'extruder'
        metadata in the samples seen, but nothing in the format rules it out)."""
        return {p.id: p.get_metadata("extruder") for p in self.parts}


@dataclass
class ModelSettings:
    root: Node

    @classmethod
    def parse(cls, xml_text: str) -> ModelSettings:
        return cls(root=Node.from_element(ET.fromstring(declare_unbound_prefixes(xml_text))))

    @property
    def objects(self) -> list[ObjectView]:
        return [ObjectView(c) for c in self.root.children if c.tag == "object"]

    def object_by_id(self, obj_id: str) -> ObjectView | None:
        for o in self.objects:
            if o.id == obj_id:
                return o
        return None

    def all_extruder_slots(self) -> set[str]:
        """Every logical color slot referenced anywhere in the file (object- and part-level)."""
        slots: set[str] = set()
        for obj in self.objects:
            if obj.extruder is not None:
                slots.add(obj.extruder)
            for part in obj.parts:
                v = part.get_metadata("extruder")
                if v is not None:
                    slots.add(v)
        return slots

    def to_xml(self) -> str:
        el = self.root.to_element()
        ET.indent(el, space="  ")
        body = ET.tostring(el, encoding="unicode")
        return XML_DECLARATION + body + "\n"


def set_plate_filament_maps(settings: ModelSettings, filament_map: list[str]) -> int:
    """Point every plate's `filament_maps` at the same extruder assignment.

    Each `<plate>` carries its own copy, space-separated, and the slicer reads
    it per plate rather than falling back to the project-wide `filament_map`.
    Leaving the plates saying "1 1 1 1 1 1" while the project routes a TPU slot
    to extruder 2 is the two disagreeing about the same thing, and the plate is
    the one that wins.

    Returns how many plates were updated.
    """
    value = " ".join(filament_map)
    updated = 0
    for plate in (c for c in settings.root.children if c.tag == "plate"):
        for node in plate.children:
            if node.tag == "metadata" and node.attrib.get("key") == "filament_maps":
                if node.attrib.get("value") != value:
                    node.attrib["value"] = value
                    updated += 1
                break
    return updated
