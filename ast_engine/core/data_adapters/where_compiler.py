"""
Definition-query compiler.

Turn the registry's structured attribute filter (where) into real SQL.

The registry parses each dataset's Definition_Query once, into a small structured form
(a WhereClause / LogicalGroup of Conditions - see config/registry/query.py).
This module does the other half: it turns that structured filter back into a
SQL WHERE string for one database at a time.

Each adapter calls compile_where() with its own SQL dialect:
  - the Oracle adapter compiles to Oracle SQL and pushes it into the SDO query;
  - the file adapter compiles to SQLite and runs it against the file's
    attributes in an in-memory table (see filter_gdf_with_sql).

Why this lives here and not next to the model: the registry (config) already
imports the adapters (core) at build time to read dataset metadata. If the
adapters imported the model back, the two packages would depend on each other.
So this compiler stays in core and never imports the model - it walks the
filter as plain data (a model's .model_dump(), or an equivalent dict), which is
all SQLAlchemy needs.
"""

from typing import Any

from sqlalchemy import and_, column, func, or_
from sqlalchemy.dialects import oracle, postgresql, sqlite

# One dialect object per database we can target. SQLAlchemy uses it to render
# the right SQL flavour (identifier quoting, value formatting, etc.).
# Oracle for BCGW, SQLite for file datasets, Postgres for potential future use
_DIALECTS = {
    "oracle": oracle.dialect(),
    "sqlite": sqlite.dialect(),
    "postgresql": postgresql.dialect(),
}


def compile_where(where: Any, dialect: str = "oracle") -> str:
    """Compile a structured where filter into a SQL WHERE string.

    where:   the dataset's structured filter - a WhereClause / LogicalGroup
             model, or the plain-dict form of one.
    dialect: which database to render for - "oracle", "sqlite" or "postgresql".

    Returns the WHERE text WITHOUT the leading "WHERE" keyword, e.g.
        "STATUS" = 'ACTIVE' AND "RANK" <> 'X'
    so the caller can drop it straight into its own query. Returns "" when the
    filter is empty.

    The values are written directly into the SQL string (literal_binds) rather
    than passed as bound parameters, because the result is handed to engines
    that take a finished WHERE string (the Oracle SDO query, an in-memory SQLite
    SELECT).
    """
    if where is None:
        return ""

    sql_dialect = _DIALECTS.get(dialect.lower())
    if sql_dialect is None:
        raise ValueError(
            f"Unsupported SQL dialect {dialect!r}; expected one of "
            f"{', '.join(sorted(_DIALECTS))}"
        )

    expression = _build(_as_dict(where))
    compiled = expression.compile(
        dialect=sql_dialect,
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)


def _as_dict(where: Any) -> dict:
    """Accept either a pydantic where model or its plain-dict form.

    Calling model_dump(by_alias=True) gives back the "and"/"or" keys (not the
    Python-safe and_/or_ field names), which is what _build walks below.
    """
    if hasattr(where, "model_dump"):
        return where.model_dump(by_alias=True)
    return where


def _build(node: dict):
    """Walk one node of the filter into a SQLAlchemy expression.

    A node is one of three shapes:
      - a logical group: {"and": [...]} or {"or": [...]} - combine the children;
      - a where clause:  {"conditions": [...]} - its conditions are AND-ed
        together (matching how several conditions in one clause read in SQL);
      - a single condition: {"field": ..., "op": ..., "value": ...}.
    """
    # A LogicalGroup model dumps both keys; only one carries a list.
    if node.get("and") is not None:
        return and_(*[_build(child) for child in node["and"]])
    if node.get("or") is not None:
        return or_(*[_build(child) for child in node["or"]])

    if node.get("conditions") is not None:
        parts = [_build_condition(c) for c in node["conditions"]]
        # Several conditions in one clause combine with AND.
        return and_(*parts) if len(parts) != 1 else parts[0]

    return _build_condition(node)


def _build_condition(cond: dict):
    """Turn one condition dict into a SQLAlchemy comparison."""
    col = column(cond["field"])
    op = cond["op"]
    value = _value(cond.get("value"))

    if op == "=":
        return col == value
    if op == "!=":
        return col != value
    if op == ">":
        return col > value
    if op == "<":
        return col < value
    if op == ">=":
        return col >= value
    if op == "<=":
        return col <= value
    if op == "in":
        return col.in_(value)
    if op == "like":
        return col.like(value)
    if op == "not_like":
        return col.notlike(value)
    if op == "between":
        return col.between(value[0], value[1])
    if op == "is_null":
        return col.is_(None)
    if op == "is_not_null":
        return col.isnot(None)
    raise ValueError(f"Unsupported operator in where filter: {op!r}")


def _value(value: Any):
    """Translate a stored condition value into something SQLAlchemy can render.

    Most values are plain text or numbers and pass straight through. The one
    special case is the CURRENT_DATE marker (stored as {"func": "current_date"}):
    it becomes SQL's CURRENT_DATE keyword, so the database fills in today's date
    itself when the query runs.
    """
    if isinstance(value, dict) and value.get("func") == "current_date":
        return func.current_date()
    return value


def filter_gdf_with_sql(gdf, where_sql: str):
    """Filter a GeoDataFrame by a SQL WHERE string, using in-memory SQLite.

    Used by file-based datasets, whose attributes are already in memory. The
    non-geometry columns are loaded into a throwaway in-memory SQLite table, the
    WHERE clause selects the matching rows, and we keep exactly those rows of the
    original GeoDataFrame - so the geometry is never touched or rewritten.

    This lets a real SQL filter (the same structured filter the registry built)
    run against a file, instead of pandas' own different query syntax.
    """
    import sqlite3

    import pandas as pd

    if gdf.empty or not where_sql:
        return gdf

    work = gdf.copy()
    # A stable row marker so we can map matching SQLite rows back to the
    # original features regardless of the GeoDataFrame's own index.
    work["__row__"] = range(len(work))
    geom_col = work.geometry.name
    attributes = pd.DataFrame(work.drop(columns=geom_col))

    conn = sqlite3.connect(":memory:")
    try:
        attributes.to_sql("data", conn, index=False)
        matched = pd.read_sql(f"SELECT __row__ FROM data WHERE {where_sql}", conn)
    finally:
        conn.close()

    keep = set(matched["__row__"].tolist())
    return work[work["__row__"].isin(keep)].drop(columns="__row__")
