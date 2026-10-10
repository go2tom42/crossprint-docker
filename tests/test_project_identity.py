from pathlib import Path
import pytest
from xml.etree import ElementTree as ET

from core.archive import ThreeMFArchive
from core.model_settings import ModelSettings
from convert.project_identity import declare_bambu_project, sanitize_bambu_plate_names
from convert.pipeline import convert


def test_plate_names_change_only_invalid_characters():
    settings = ModelSettings.parse('<config><plate><metadata key="plater_name" value="Lid / Plexiglas"/><metadata key="locked" value="1"/></plate><plate><metadata key="plater_name" value="Joints (TPU)"/></plate></config>')
    assert sanitize_bambu_plate_names(settings) == ['Lid / Plexiglas -> Lid - Plexiglas']
    assert settings.root.children[0].children[1].attrib['value'] == '1'
    assert settings.root.children[1].children[0].attrib['value'] == 'Joints (TPU)'


def test_identity_preserves_geometry_and_source_and_is_idempotent():
    mesh = '<resources><object id="1"><mesh/></object></resources><build><item objectid="1"/></build>'
    source = '<model><metadata name="Application">Snapmaker_Orca-2.4.0</metadata>' + mesh + '</model>'
    archive = ThreeMFArchive()
    archive.set_text('3D/3dmodel.model', source)
    assert declare_bambu_project(archive)
    output = archive.get_text('3D/3dmodel.model')
    assert mesh in output
    metadata = {e.attrib['name']: e.text for e in ET.fromstring(output).findall('metadata')}
    assert metadata['Application'].startswith('BambuStudio-')
    assert metadata['Crossprint:SourceApplication'] == 'Snapmaker_Orca-2.4.0'
    assert not declare_bambu_project(archive)
    assert archive.get_text('3D/3dmodel.model') == output


@pytest.mark.parametrize('target', ['h2d', 'h2c'])
def test_real_enclosure_keeps_all_plate_memberships(target):
    path = Path.home() / 'Downloads/FilamentEnclosure_PLA_V1.2_for_SNORCA_V2.4.0.3mf'
    if not path.exists():
        pytest.skip('enclosure sample unavailable')
    with ThreeMFArchive.open(path) as source:
        original = ModelSettings.parse(source.get_text('Metadata/model_settings.config'))
        archive, _ = convert(path, target)
        try:
            settings = ModelSettings.parse(archive.get_text('Metadata/model_settings.config'))
            old_plates = [p for p in original.root.children if p.tag == 'plate']
            new_plates = [p for p in settings.root.children if p.tag == 'plate']
            assert len(old_plates) == len(new_plates) == 14
            for old, new in zip(old_plates, new_plates):
                assert [n for n in old.children if n.tag == 'model_instance'] == [n for n in new.children if n.tag == 'model_instance']
            assert not sanitize_bambu_plate_names(settings)
            model = ET.fromstring(archive.get_text('3D/3dmodel.model'))
            ns = {'m': 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
            assert len(model.findall('m:build/m:item', ns)) == 40
            assert any(e.attrib.get('name') == 'Application' and e.text.startswith('BambuStudio-') for e in model)
            for name in source.names():
                if name.startswith('3D/Objects/'):
                    assert source.get_bytes(name) == archive.get_bytes(name)
        finally:
            archive.close()
