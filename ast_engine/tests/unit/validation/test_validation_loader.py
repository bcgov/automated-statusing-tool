"""Real YAML parsing, policy validation, component switches, and source path resolution."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError

from ast_engine.config.validation.validation_loader import load_validation_config
from ast_engine.core.validation.exceptions import ValidationConfigError
from ast_engine.core.validation.models import ValidationConfig
from ast_engine.tests.unit.validation.validation_cases import layer_doc, rule, write_policy

pytestmark = pytest.mark.unit


def load(root, path, *, geometry=True, spatial=True):
    return load_validation_config(
        path, geometry_validation=geometry, spatial_validation=spatial, config_root=root
    )


def valid_document():
    return {"geometry": {"rules": [rule(threshold_ha=0.1)]}, "spatial": [layer_doc()]}


@pytest.mark.parametrize(
    "geometry,spatial", [(True, True), (True, False), (False, True), (False, False)]
)
def test_component_switches_select_independent_typed_sections(tmp_path, geometry, spatial):
    path = write_policy(tmp_path / "policy.yaml", valid_document())
    c = load(tmp_path, path, geometry=geometry, spatial=spatial)
    assert isinstance(c, ValidationConfig) and c.schema_version == 1
    assert (c.geometry is not None) == geometry and (c.spatial is not None) == spatial
    if geometry:
        assert c.geometry.rules[0].threshold_ha == 0.1
    if spatial:
        assert c.spatial[0].datasource == str((tmp_path / "units.gpkg").resolve())


@pytest.mark.parametrize("path", [None, "does-not-exist.yaml"])
def test_both_disabled_require_neither_document_nor_absolute_root(path):
    assert load(Path("unused"), path, geometry=False, spatial=False) == ValidationConfig()


@pytest.mark.parametrize("path", [None, "", "   "])
def test_an_enabled_section_requires_a_nonblank_path(tmp_path, path):
    with pytest.raises(ValidationConfigError, match="config path is required"):
        load(tmp_path, path)


def test_policy_and_file_sources_use_config_root(tmp_path, monkeypatch):
    root = tmp_path / "app"
    elsewhere = tmp_path / "unrelated"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    absolute_source = tmp_path / "elsewhere.gpkg"
    table = "nr_regions"
    policy_path = write_policy(
        root / "policy" / "validation.yaml",
        {
            "spatial": [
                layer_doc("relative", datasource="data/units.gpkg"),
                layer_doc("absolute", datasource=str(absolute_source)),
                layer_doc("oracle", datasource=table, data_adapter="oracle"),
            ]
        },
    )

    config = load(root, "policy/validation.yaml", geometry=False)

    assert [layer.datasource for layer in config.spatial] == [
        str((root / "data/units.gpkg").resolve()),
        str(absolute_source.resolve()),
        table,
    ]
    assert load(root, policy_path, geometry=False) == config


@pytest.mark.parametrize("absolute_policy", [False, True])
def test_loading_policy_requires_absolute_config_root(tmp_path, absolute_policy):
    path = tmp_path / "validation.yaml" if absolute_policy else Path("validation.yaml")

    with pytest.raises(ValueError, match="config_root must be an absolute path"):
        load(Path("relative"), path, geometry=False)


@pytest.mark.parametrize(
    "section,value",
    [("geometry", None), ("geometry", "missing"), ("spatial", None), ("spatial", "missing")],
)
def test_enabled_section_must_exist_and_not_be_null(tmp_path, section, value):
    doc = valid_document()
    if value is None:
        doc[section] = None
    else:
        del doc[section]
    with pytest.raises(ValidationConfigError, match=rf"'{section}' section is missing or null"):
        load(tmp_path, write_policy(tmp_path / "policy.yaml", doc))


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_schema_version_rejects_wrong_type_or_unknown_format_on_otherwise_valid_policy(
    tmp_path, version
):
    doc = valid_document()
    doc["schema_version"] = version
    with pytest.raises(ValidationConfigError) as error:
        load(tmp_path, write_policy(tmp_path / "policy.yaml", doc))
    assert isinstance(error.value.__cause__, ValidationError)
    assert error.value.__cause__.errors()[0]["loc"] == ("schema_version",)


@pytest.mark.parametrize(
    "yaml_text,key",
    [
        ("geometry: null\ngeometry: null\n", "geometry"),
        ("spatial:\n- name: units\n  rules:\n    overlap: error\n    overlap: info\n", "overlap"),
    ],
)
def test_duplicate_yaml_keys_are_rejected_at_parse_time_with_location(tmp_path, yaml_text, key):
    path = tmp_path / "dupes.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValidationConfigError, match=f"duplicate YAML key '{key}'") as error:
        load(tmp_path, path)
    cause = error.value.__cause__
    assert isinstance(cause, ConstructorError)
    assert cause.context_mark.line < cause.problem_mark.line
    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "contents,cause",
    [
        (b"geometry: [", yaml.YAMLError),
        (b"\xff", UnicodeError),
        (None, OSError),
    ],
)
def test_load_errors_include_the_policy_path_and_original_cause(tmp_path, contents, cause):
    path = tmp_path / "broken.yaml"
    if contents is not None:
        path.write_bytes(contents)
    with pytest.raises(ValidationConfigError) as error:
        load(tmp_path, path)
    assert str(path) in str(error.value) and isinstance(error.value.__cause__, cause)


@pytest.mark.parametrize("text", ["", "[]", "plain text"])
def test_yaml_document_must_be_a_mapping(tmp_path, text):
    path = tmp_path / "not-a-policy.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationConfigError, match="expected a YAML mapping"):
        load(tmp_path, path)


@pytest.mark.parametrize(
    "change,location",
    [
        ("duplicate_rules", "geometry"),
        ("duplicate_layers", "spatial"),
        ("unknown_section", "layers"),
        ("empty_geometry", "geometry"),
        ("bad_disabled_layer", "spatial"),
    ],
)
def test_model_errors_are_not_silenced_by_disabling_a_section(tmp_path, change, location):
    doc = valid_document()
    if change == "duplicate_rules":
        doc["geometry"]["rules"].append(dict(doc["geometry"]["rules"][0]))
    elif change == "duplicate_layers":
        doc["spatial"].append(dict(doc["spatial"][0]))
    elif change == "unknown_section":
        doc["layers"] = []
    elif change == "empty_geometry":
        doc["geometry"]["rules"] = []
    else:
        doc["spatial"][0]["scope"] = "feature"
    with pytest.raises(ValidationConfigError) as error:
        load(tmp_path, write_policy(tmp_path / "policy.yaml", doc), spatial=False)
    assert isinstance(error.value.__cause__, ValidationError)
    details = error.value.__cause__.errors()
    if change == "duplicate_layers":
        # Unique layer names is a whole-model after-validator, so its location is ().
        assert any(e["loc"] == () and "layer names must be unique" in e["msg"] for e in details)
    else:
        assert any(e["loc"][:1] == (location,) for e in details)


def test_same_loader_returns_independent_aoi_and_results_policies(tmp_path):
    aoi = write_policy(tmp_path / "aoi.yaml", valid_document())
    results = write_policy(
        tmp_path / "results.yaml",
        {
            "geometry": {
                "rules": [
                    rule("max_area", rule_id="large_result", scope="footprint", threshold_ha=20.0)
                ]
            }
        },
    )
    first = load(tmp_path, aoi)
    second = load(tmp_path, results, spatial=False)
    assert first.spatial[0].name == "units" and second.spatial is None
    assert (
        first.geometry.rules[0].id == "minimum_part"
        and second.geometry.rules[0].id == "large_result"
    )


def test_shipped_aoi_policy_loads_without_opening_reference_sources():
    from ast_engine.config.validation import validation_loader

    folder = Path(validation_loader.__file__).resolve().parent
    c = load(folder, "aoi_validation.yaml")
    assert c.geometry is not None and c.geometry.rules
    assert c.spatial is not None and all(item.rules is not None for item in c.spatial)


def test_unknown_caller_profile_raises_config_error(tmp_path):
    with pytest.raises(ValidationConfigError, match="Unknown validation profile: 'frontend'") as err:
        load_validation_config(
            None,
            geometry_validation=False,
            spatial_validation=False,
            config_root=tmp_path,
            profile="frontend",
        )

    assert isinstance(err.value.__cause__, ValueError)
