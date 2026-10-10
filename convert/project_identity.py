"""Declare the target project dialect without reserializing mesh XML."""
import re

from core.archive import ThreeMFArchive
from core.model_settings import ModelSettings


def declare_bambu_project(archive: ThreeMFArchive) -> bool:
    # Bambu's importer only loads project config/plates when Application
    # starts with BambuStudio-. This is a dialect marker, not authorship;
    # retain the source Application separately for provenance.
    text = archive.get_text("3D/3dmodel.model")
    if text is None:
        return False
    pattern = re.compile(r'(<metadata\b[^>]*\bname=[\"\x27]Application[\"\x27][^>]*>)(.*?)(</metadata\s*>)', re.S)
    match = pattern.search(text)
    if match and match[2].startswith("BambuStudio-"):
        return False
    marker = '<metadata name="Application">BambuStudio-01.00.00.00</metadata>'
    if match:
        replacement = marker + '\n<metadata name="Crossprint:SourceApplication">' + match[2] + '</metadata>'
        text = text[:match.start()] + replacement + text[match.end():]
    else:
        root = re.search(r'<model\b[^>]*>', text)
        if root is None:
            raise ValueError("Cannot declare project dialect: missing model root")
        text = text[:root.end()] + '\n' + marker + text[root.end():]
    archive.set_text("3D/3dmodel.model", text)
    return True


def sanitize_bambu_plate_names(settings: ModelSettings) -> list[str]:
    """Bambu rejects filename-reserved characters in plate display names."""
    changes = []
    for plate in settings.root.children:
        if plate.tag != "plate":
            continue
        for meta in plate.children:
            if meta.tag != "metadata" or meta.attrib.get("key") != "plater_name":
                continue
            original = meta.attrib.get("value", "")
            clean = re.sub(r'[<>:/\\|?*"\x00-\x1f]', '-', original)
            if clean != original:
                meta.attrib["value"] = clean
                changes.append(f"{original} -> {clean}")
    return changes
