"""Bootstrap a real builder and cache. Only database I/O is replaced."""

from types import MappingProxyType, SimpleNamespace
from unittest.mock import Mock

import oracledb
import pytest
from pydantic import SecretStr
from shapely.geometry import box

from ast_engine.config.settings import Settings
from ast_engine.config.validation import startup
from ast_engine.core.data_adapters import oracle as oracle_package
from ast_engine.config.validation import startup
from ast_engine.core.validation.exceptions import ValidationConfigError
from ast_engine.core.validation.schema import ValidationProfile as Profile
from ast_engine.core.validation.spatial.reference_loader import load_reference_layers
from ast_engine.core.validation.spatial.spatial_validation import SpatialValidationError
from ast_engine.tests.unit.validation.validation_cases import (
    CRS,
    build,
    frame,
    layer,
    layer_doc,
    rule,
    write_policy,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def offline_oracle(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("This test must not open a real Oracle connection")

    monkeypatch.setattr(oracledb, "connect", unexpected)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(startup, "PROJECT_ROOT", tmp_path)

    return Settings.model_construct(
        aoi_validation_config_path="policy.yaml",
        validate_aoi_geometry=False,
        validate_aoi_spatial=True,
        system_crs=CRS,
    )


def test_disabled_policy_requires_no_files_or_adapters(settings):
    settings.validate_aoi_spatial = False
    settings.aoi_validation_config_path = None
    builder = startup.create_aoi_builder(settings, profile=Profile.RUNTIME)
    result = build(builder, box(0, 0, 1, 1))
    assert result.is_valid and result.validation.issues == ()
    assert not result.validation.geometry_checks_run and not result.validation.spatial_checks_run
    assert builder.validator.required_spatial_parameters == frozenset()


def test_geometry_only_installs_real_validator_without_touching_configured_oracle(
    settings, tmp_path
):
    write_policy(
        tmp_path / "policy.yaml",
        {
            "geometry": {"rules": [rule(rule_id="too_small", threshold_ha=0.1)]},
            "spatial": [layer_doc(data_adapter="oracle", datasource="WHSE.UNITS")],
        },
    )
    settings.validate_aoi_geometry, settings.validate_aoi_spatial = True, False
    result = build(startup.create_aoi_builder(settings, profile=Profile.RUNTIME), box(0, 0, 1, 1))
    assert [f.code for f in result.errors] == ["TOO_SMALL"]
    assert result.validation.geometry_checks_run and not result.validation.spatial_checks_run


def test_configuration_failure_precedes_adapter_reads(settings):
    adapter = Mock()
    with pytest.raises(ValidationConfigError, match="policy.yaml"):
        startup.create_aoi_builder(settings, profile=Profile.RUNTIME, adapters={"oracle": adapter})
    adapter.read.assert_not_called()


def test_partial_adapter_injection_and_real_geopackage_cache(settings, tmp_path):
    file_path = tmp_path / "coverage.gpkg"
    frame(box(0, 0, 10, 10)).to_file(file_path, driver="GPKG", index=False)
    world = Mock()
    world.read.return_value = frame(box(-100, -100, 100, 100))
    supplied = MappingProxyType({"oracle": world})
    write_policy(
        tmp_path / "policy.yaml",
        {
            "spatial": [
                layer_doc("file_coverage", datasource=file_path.name),
                layer_doc("oracle_coverage", data_adapter="oracle", datasource="WHSE.COVERAGE"),
            ]
        },
    )
    builder = startup.create_aoi_builder(settings, profile=Profile.RUNTIME, adapters=supplied)
    file_path.unlink()  # Results can only come from the prepared in-memory references now.
    assert build(builder, box(1, 1, 2, 2)).is_valid
    outside = build(builder, box(20, 20, 21, 21))
    assert [(i.code, i.layer_name) for i in outside.errors] == [
        ("SPATIAL_NO_OVERLAP", "file_coverage")
    ]
    assert dict(supplied) == {"oracle": world}
    world.read.assert_called_once()


@pytest.mark.parametrize(
    "profile,checked,blocked",
    [
        (Profile.RUNTIME, ("province", "management"), False),
        (Profile.SUBMISSION, ("province", "management", "blocker"), True),
    ],
)
def test_profile_controls_execution_but_all_sources_are_loaded_once_per_builder(
    settings, tmp_path, profile, checked, blocked
):
    t = "WHSE.UNITS"
    write_policy(
        tmp_path / "policy.yaml",
        {
            "spatial": [
                layer_doc("province", data_adapter="oracle", datasource=t),
                layer_doc(
                    "management",
                    data_adapter="oracle",
                    datasource=t,
                    id_field="ORG_UNIT",
                    expected_from="expected_unit_ids",
                    rules={"outside_expected": "error"},
                ),
                layer_doc(
                    "blocker",
                    data_adapter="oracle",
                    datasource="WHSE.BLOCKERS",
                    run_in=["submission"],
                    tags=["showstopper"],
                    rules={"overlap": "error"},
                ),
            ]
        },
    )
    sources = {
        t: frame(box(0, 0, 10, 10), ORG_UNIT=["RCB"]),
        "WHSE.BLOCKERS": frame(box(0, 0, 4, 4)),
    }
    adapter = Mock()
    adapter.read.side_effect = lambda **kw: sources[kw["table"]]
    builder = startup.create_aoi_builder(settings, profile=profile, adapters={"oracle": adapter})
    assert builder.validator.required_spatial_parameters == frozenset({"expected_unit_ids"})
    for _ in range(2):
        result = build(builder, box(1, 1, 2, 2), parameters={"expected_unit_ids": ["RCB"]})
        assert result.validation.checked_spatial_layers == checked
        assert result.validation.profile == profile
        assert result.has_errors is blocked
        assert [(i.code, i.tags) for i in result.errors] == (
            [("SPATIAL_OVERLAP", ("showstopper",))] if blocked else []
        )
    assert adapter.read.call_count == 2
    by_table = {c.kwargs["table"]: c.kwargs for c in adapter.read.call_args_list}
    assert set(by_table) == set(sources)
    assert by_table[t]["read_options"].keep_columns == ["ORG_UNIT"]
    for kwargs in by_table.values():
        assert kwargs["target_crs"] == CRS
        assert kwargs["read_options"].spatial_filter is None


def test_reference_loader_deduplicates_by_adapter_and_source_and_unions_requested_fields():
    policies = (
        layer("file", data_adapter="file", datasource="same"),
        layer(
            "oracle_z",
            datasource="same",
            data_adapter="oracle",
            id_field="ZONE",
            rules={"multiple_units": "warning"},
        ),
        layer(
            "oracle_i",
            datasource="same",
            data_adapter="oracle",
            id_field="ID",
            rules={"multiple_units": "warning"},
        ),
    )
    f, o = Mock(), Mock()
    f.read.return_value, o.read.return_value = frame(), frame(ID=[], ZONE=[])
    cache = load_reference_layers(policies, adapters={"file": f, "oracle": o}, target_crs=CRS)
    assert set(cache) == {("file", "same"), ("oracle", "same")}
    f.read.assert_called_once()
    o.read.assert_called_once()
    fk, ok = f.read.call_args.kwargs, o.read.call_args.kwargs
    assert fk["path"] == "same" and fk["read_options"].keep_columns is None
    assert (ok["table"], ok["read_options"].keep_columns) == (
        "same",
        ["ID", "ZONE"],
    )
    assert all(
        k["target_crs"] == CRS and k["read_options"].spatial_filter is None for k in (fk, ok)
    )
    assert load_reference_layers(None, adapters={}, target_crs=CRS) == {}
    with pytest.raises(SpatialValidationError, match="No startup adapter"):
        load_reference_layers(policies, adapters={}, target_crs=CRS)


@pytest.mark.parametrize("borrow", [False, True], ids=["owned", "borrowed"])
@pytest.mark.parametrize("read_fails", [False, True], ids=["success", "read-error"])
def test_oracle_handle_ownership_on_success_and_failure(
    settings, tmp_path, monkeypatch, borrow, read_fails
):
    write_policy(
        tmp_path / "policy.yaml",
        {
            "spatial": [
                layer_doc("province", data_adapter="oracle", datasource="WHSE.PROVINCE"),
            ]
        },
    )
    db, cursor = Mock(), Mock()
    db.cursor.return_value = cursor
    connect = Mock(return_value=db)
    monkeypatch.setattr(oracledb, "connect", connect)
    reader = Mock()
    failure = OSError("reference unavailable")

    def read_while_open(**kwargs):
        cursor.close.assert_not_called()
        db.close.assert_not_called()
        if read_fails:
            raise failure
        return frame(box(0, 0, 10, 10))

    reader.read.side_effect = read_while_open
    construct_adapter = Mock(return_value=reader)
    monkeypatch.setattr(oracle_package, "OracleAdapter", construct_adapter)

    if borrow:
        # The outer job opens this real wrapper against the fake driver.
        session = startup.OracleConnection("job", "test-only", "example.invalid/test")
    else:
        session = None
        settings.oracle_user, settings.oracle_password = "test-user", SecretStr("test-only")
        settings.oracle_host, settings.oracle_port, settings.oracle_database = (
            "example.invalid",
            1521,
            "TEST",
        )

    try:
        if read_fails:
            with pytest.raises(SpatialValidationError, match="WHSE.PROVINCE") as error:
                startup.create_aoi_builder(settings, profile=Profile.RUNTIME, connection=session)
            assert error.value.__cause__ is failure
        else:
            builder = startup.create_aoi_builder(
                settings, profile=Profile.RUNTIME, connection=session
            )
            assert build(builder, box(1, 1, 2, 2)).is_valid
            assert [i.code for i in build(builder, box(20, 20, 21, 21)).errors] == [
                "SPATIAL_NO_OVERLAP"
            ]
        construct_adapter.assert_called_once_with(connection=db, cursor=cursor)
        connect.assert_called_once()
        reader.read.assert_called_once()
        if borrow:
            assert session.connection is db and session.cursor is cursor
            db.close.assert_not_called()
            cursor.close.assert_not_called()
        else:
            assert connect.call_args.kwargs["dsn"] == "example.invalid:1521/TEST"
            db.close.assert_called_once_with()
            cursor.close.assert_called_once_with()
    finally:
        if borrow:
            session.close()


@pytest.mark.parametrize("connection,cursor", [(None, object()), (object(), None)])
def test_borrowed_oracle_wrapper_must_already_be_open(settings, tmp_path, connection, cursor):
    write_policy(tmp_path / "policy.yaml", {"spatial": [layer_doc(data_adapter="oracle")]})
    with pytest.raises(ValueError, match="open connection and cursor"):
        startup.create_aoi_builder(
            settings,
            profile=Profile.RUNTIME,
            connection=SimpleNamespace(connection=connection, cursor=cursor),
        )


def test_oracle_settings_required_only_when_creating_the_session(settings, tmp_path):
    write_policy(tmp_path / "policy.yaml", {"spatial": [layer_doc(data_adapter="oracle")]})
    with pytest.raises(ValueError, match="Oracle settings are required"):
        startup.create_aoi_builder(settings, profile=Profile.RUNTIME)
