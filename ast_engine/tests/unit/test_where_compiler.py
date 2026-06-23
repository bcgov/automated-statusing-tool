#\tests\unit\test_where_compiler.py
"""
Definition-query parser + compiler tests.

Covers the two halves of attribute filtering:
- the parser (config/registry/query.py) that reads a legacy Definition_Query
  string into the structured where model, including the CURRENT_DATE marker;
- the compiler (core/data_adapters/where_compiler.py) that turns that model
  back into a SQL WHERE string per database, and the in-memory SQLite filter
  the file adapter uses.

HOW TO EXTEND:
-------------
1. Add a row to test_compile_supports_every_operator for a new operator.
2. Keep test names short and readable.
3. Build the where model directly (WhereClause/Condition) when you want to test
   the compiler on its own; go through definition_to_where when you also want to
   test the parser.
"""
import geopandas as gpd
import pytest
from shapely.geometry import Point

from ast_engine.config.registry.query import (
    Condition,
    CurrentDate,
    WhereClause,
    definition_to_where,
)
from ast_engine.core.data_adapters.where_compiler import (
    compile_where,
    filter_gdf_with_sql,
)

# Tags every test in this file as "unit"
pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Compiler - every operator in the model
# (built directly so the compiler is tested on its own; the parser does not
# yet produce BETWEEN, but the compiler must still handle it. Oracle and the
# SQLite file filter render these the same, so one expected value covers both.)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "op, value, expected",
    [
        ("=", "ACTIVE", "\"X\" = 'ACTIVE'"),
        ("!=", "Z", "\"X\" != 'Z'"),
        (">", 5, '"X" > 5'),
        ("<", 5, '"X" < 5'),
        (">=", 5, '"X" >= 5'),
        ("<=", 5, '"X" <= 5'),
        ("in", ["H", "X"], "\"X\" IN ('H', 'X')"),
        ("like", "%Caribou%", "\"X\" LIKE '%Caribou%'"),
        ("not_like", "%G", "\"X\" NOT LIKE '%G'"),
        ("between", [1, 5], '"X" BETWEEN 1 AND 5'),
        ("is_null", None, '"X" IS NULL'),
        ("is_not_null", None, '"X" IS NOT NULL'),
    ],
)
def test_compile_supports_every_operator(op, value, expected):
    clause = WhereClause(conditions=[Condition(field="X", op=op, value=value)])
    assert compile_where(clause, "oracle") == expected
    assert compile_where(clause, "sqlite") == expected


def test_compile_escapes_quotes_in_values():
    """Values are escaped, so a value with an apostrophe cannot break the SQL."""
    clause = WhereClause(conditions=[Condition(field="N", op="=", value="O'Brien")])
    assert compile_where(clause, "oracle") == "\"N\" = 'O''Brien'"


def test_compile_multiple_conditions_in_clause_are_anded():
    """Several conditions in one clause combine with AND."""
    clause = WhereClause(
        conditions=[
            Condition(field="A", op="=", value="x"),
            Condition(field="B", op="=", value="y"),
        ]
    )
    assert compile_where(clause, "oracle") == "\"A\" = 'x' AND \"B\" = 'y'"


def test_compile_unknown_dialect_raises():
    clause = WhereClause(conditions=[Condition(field="A", op="=", value="x")])
    with pytest.raises(ValueError):
        compile_where(clause, "mysql")


def test_compile_none_where_is_empty():
    assert compile_where(None) == ""


# ---------------------------------------------------------------------------
# Parser + compiler together - AND/OR nesting and precedence
# ---------------------------------------------------------------------------

def test_compile_nested_and_or_precedence():
    """(A AND B) OR C keeps its meaning: AND binds tighter, so no extra parens."""
    where = definition_to_where("(\"RANK\" <> 'H' AND \"RANK\" <> 'X') OR \"RANK\" IS NULL")
    assert (
        compile_where(where, "oracle")
        == "\"RANK\" != 'H' AND \"RANK\" != 'X' OR \"RANK\" IS NULL"
    )


def test_compile_or_inside_and_gets_parens():
    """A AND (B OR C) must keep the brackets, or the meaning changes."""
    where = definition_to_where("\"A\" = 'x' AND (\"B\" = 'y' OR \"C\" = 'z')")
    assert (
        compile_where(where, "oracle")
        == "\"A\" = 'x' AND (\"B\" = 'y' OR \"C\" = 'z')"
    )


# ---------------------------------------------------------------------------
# CURRENT_DATE marker - parsed, compiled, and stays "today" across a save/load
# ---------------------------------------------------------------------------

def test_parser_current_date_produces_marker():
    """CURRENT_DATE parses to the symbolic marker, not a literal."""
    where = definition_to_where('"EXPIRY_DATE" > CURRENT_DATE')
    assert isinstance(where.conditions[0].value, CurrentDate)


def test_compile_current_date_keyword():
    """The marker renders as the bare CURRENT_DATE keyword for each database."""
    clause = WhereClause(
        conditions=[Condition(field="EXPIRY_DATE", op=">", value=CurrentDate())]
    )
    assert compile_where(clause, "oracle") == '"EXPIRY_DATE" > CURRENT_DATE'
    assert compile_where(clause, "sqlite") == '"EXPIRY_DATE" > CURRENT_DATE'


def test_current_date_round_trips_without_baking_a_date():
    """Saving and reloading the model keeps the marker - no fixed date is
    written in, so a stored registry never goes stale."""
    where = definition_to_where('"EXPIRY_DATE" > CURRENT_DATE')
    dumped = where.model_dump(by_alias=True)
    assert dumped["conditions"][0]["value"] == {"func": "current_date"}

    reloaded = WhereClause(**dumped)
    assert compile_where(reloaded, "oracle") == '"EXPIRY_DATE" > CURRENT_DATE'


# ---------------------------------------------------------------------------
# In-memory SQLite filter (how file datasets apply the where)
# ---------------------------------------------------------------------------

def _sample_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"STATUS": ["ACTIVE", "EXPIRED", "ACTIVE"], "RANK": ["H", "X", "A"]},
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
        crs="EPSG:3005",
    )


def test_filter_gdf_with_sql_keeps_matching_rows_and_geometry():
    gdf = _sample_gdf()
    where = definition_to_where("\"STATUS\" = 'ACTIVE' AND \"RANK\" <> 'X'")
    out = filter_gdf_with_sql(gdf, compile_where(where, "sqlite"))

    assert len(out) == 2
    assert list(out["STATUS"]) == ["ACTIVE", "ACTIVE"]
    assert out.geometry.notna().all()


def test_filter_gdf_with_sql_no_match_returns_empty():
    gdf = _sample_gdf()
    where = definition_to_where("\"STATUS\" = 'CANCELLED'")
    out = filter_gdf_with_sql(gdf, compile_where(where, "sqlite"))
    assert len(out) == 0


def test_filter_gdf_with_sql_empty_input_is_unchanged():
    empty = gpd.GeoDataFrame({"A": []}, geometry=[], crs="EPSG:3005")
    out = filter_gdf_with_sql(empty, '"A" = 1')
    assert len(out) == 0
