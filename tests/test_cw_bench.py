import json
from pathlib import Path

from lmts.core.cw_bench import compare_cw, discover_cw_sources, load_cw_source


def _source_document(*, identity_id: str = "EXAMPLE", version: str = "1.0.0") -> dict:
    return {
        "format": {"contract_format": "CANONICAL_CONTRACT", "format_version": "2.1"},
        "identity": {"id": identity_id, "name": "Example", "type": "system_architecture", "version": version},
        "status": "unlocked",
        "entities": [
            {
                "id": "#FILE:src:main.py",
                "name": "main.py",
                "entity_type_ref": "code",
                "properties": [
                    {
                        "id": "FUNCTION_MAIN",
                        "property_type_ref": "function",
                        "value": {
                            "function_type_ref": "main",
                            "properties": {"name": "main", "qualified_name": "main.py:main"},
                        },
                    },
                    {
                        "id": "EVENT_START",
                        "property_type_ref": "event",
                        "value": {"event_type_ref": "start"},
                    },
                    {
                        "id": "EFFECT_RENDER",
                        "property_type_ref": "effect",
                        "value": {"effect_type_ref": "render"},
                    },
                    {
                        "id": "LINK_HANDLER",
                        "property_type_ref": "link",
                        "value": {"link_type_ref": "event_handler"},
                    },
                ],
            }
        ],
    }


def test_load_cw_source_uses_identity_version_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "example.json"
    document = _source_document()
    path.write_text(json.dumps(document), encoding="utf-8")

    source = load_cw_source(path)

    assert source.ref == "EXAMPLE@1.0.0"
    assert source.identity_id == "EXAMPLE"
    assert source.version == "1.0.0"
    assert len(source.digest) == 64


def test_discover_cw_sources_rejects_duplicate_source_refs(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "nested" / "second.json"
    second.parent.mkdir()
    first.write_text(json.dumps(_source_document()), encoding="utf-8")
    second.write_text(json.dumps(_source_document()), encoding="utf-8")

    try:
        discover_cw_sources(tmp_path)
    except ValueError as exc:
        assert "duplicate CW source ref" in str(exc)
    else:
        raise AssertionError("duplicate CW source refs were accepted")


def test_compare_cw_treats_source_suffix_as_noncanonical_identity() -> None:
    expected = _source_document()
    actual = _source_document(identity_id="CIC_IMPORTED_CODE_MODEL", version="0.3.0")
    actual["entities"][0]["id"] = "#FILE:src:main"
    actual["entities"][0]["name"] = "main"

    comparison = compare_cw(expected, actual)

    assert comparison.dimensions["cw_file_identity"] == 100.0
    assert comparison.dimensions["cw_functions"] == 100.0
    assert comparison.dimensions["cw_events"] == 100.0
    assert comparison.dimensions["cw_effects"] == 100.0
    assert comparison.dimensions["cw_link_semantics"] == 100.0
    assert comparison.exact is True


def test_compare_cw_reports_missing_semantics() -> None:
    expected = _source_document()
    actual = _source_document(identity_id="CIC_IMPORTED_CODE_MODEL", version="0.3.0")
    actual["entities"][0]["id"] = "#FILE:src:main"
    actual["entities"][0]["properties"] = [
        prop
        for prop in actual["entities"][0]["properties"]
        if prop.get("property_type_ref") != "effect"
    ]

    comparison = compare_cw(expected, actual)

    assert comparison.dimensions["cw_effects"] == 0.0
    assert comparison.exact is False
    assert comparison.evidence["cw_effects"]["missing"] == ["render"]
