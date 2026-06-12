from typing import Optional, List, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import sqlglot
from sqlglot import exp

import logging
logger = logging.getLogger(__name__)

Operator = Literal[
    "=",
    "!=",
    ">",
    "<",
    ">=",
    "<=",
    "in",
    "like",
    "not_like",
    "between",
    "is_null",
    "is_not_null",
]

class Condition(BaseModel):
    field: str
    op: Operator
    value: Optional[Union[str, int, float, List[Union[str, int, float]]]] = None

    @field_validator("value")
    @classmethod
    def validate_value(cls, v, info):
        op = info.data.get("op")
        logger.debug(f"Validating Condition with operator {op} and value {v}")

        if op in ("is_null", "is_not_null"):
            if v is not None:
                raise ValueError(f"{op} must not include a value")

        elif op == "between":
            if not isinstance(v, list) or len(v) != 2:
                raise ValueError("between requires a list of two values")

        elif op == "in":
            if not isinstance(v, list):
                raise ValueError("in requires a list of values")

        elif op in ("like", "not_like"):
            if not isinstance(v, str):
                raise ValueError("like/not_like require a string")

        else:
            if v is None:
                raise ValueError(f"{op} requires a value")

        return v

    

class LogicalGroup(BaseModel):
    and_: Optional[List["WhereClause"]] = Field(default=None, alias="and")
    or_: Optional[List["WhereClause"]] = Field(default=None, alias="or")

    @model_validator(mode="after")
    def validate_group(self):
        if not self.and_ and not self.or_:
            raise ValueError("LogicalGroup must define 'and' or 'or'")
    

class WhereClause(BaseModel):
    conditions: List[Condition]


def build_where(clause, table):
    from sqlalchemy import and_, or_

    if "and" in clause:
        return and_(*[build_where(c, table) for c in clause["and"]])

    if "or" in clause:
        return or_(*[build_where(c, table) for c in clause["or"]])

    # condition
    col = getattr(table.c, clause["field"])
    op = clause["op"]
    val = clause.get("value")

    if op == "=":
        return col == val

    if op == "in":
        return col.in_(val)

    raise NotImplementedError(op)


def normalize(sql: str) -> str:
    # remove double quotes around column names
    # Thanks AI
    sql = re.sub(r'"([^"]+)"', r'\1', sql)
    return sql.strip()


def split_clauses(sql: str):
    # detect logical operator
    if " AND " in sql:
        return "and", sql.split(" AND ")
    elif " OR " in sql:
        return "or", sql.split(" OR ")
    else:
        return None, [sql]


def sqlglot_to_where(expression):
    from .query import Condition, WhereClause, LogicalGroup

    if isinstance(expression, exp.And):
        return {
            "and": [
                sqlglot_to_where(expression.left),
                sqlglot_to_where(expression.right),
            ]
        }

    if isinstance(expression, exp.Or):
        return {
            "or": [
                sqlglot_to_where(expression.left),
                sqlglot_to_where(expression.right),
            ]
        }

    if isinstance(expression, exp.EQ):
        return {
            "conditions": [
                Condition(
                    field=expression.left.name,
                    op="=",
                    value=expression.right.name if expression.right.is_string else expression.right.this,
                )
            ]
        }

    if isinstance(expression, exp.In):
        return {
            "conditions": [
                Condition(
                    field=expression.this.name,
                    op="in",
                    value=[v.name if v.is_string else v.this for v in expression.expressions],
                )
            ]
        }

    raise NotImplementedError(f"Unsupported expression: {type(expression)}")


def _convert(expr):
    """
    Converts a sqlglot expression into WhereClause or LogicalGroup.

    Supported:
    - AND / OR
    - =, >, <, >=, <=
    - IN
    - LIKE / NOT LIKE
    """

    # ------------------------
    # Logical groups
    # ------------------------
    
    if isinstance(expr, exp.Is):
        if isinstance(expr.expression, exp.Null):
            return WhereClause(
                conditions=[
                    Condition(
                        field=expr.this.name,
                        op="is_null",
                    )
                ]
            )

    if isinstance(expr, exp.And):
        return LogicalGroup(**{
            "and": [
                _convert(expr.left),
                _convert(expr.right),
            ]
        })

    if isinstance(expr, exp.Or):
        return LogicalGroup(**{
            "or": [
                _convert(expr.left),
                _convert(expr.right),
            ]
        })

    # ------------------------
    # NOT wrapper
    # ------------------------
    if isinstance(expr, exp.Not):
        inner = expr.this

        # Handle NOT LIKE
        if isinstance(inner, exp.Like):
            return WhereClause(
                conditions=[
                    Condition(
                        field=inner.this.name,
                        op="not_like",
                        value=_get_value(inner.expression),
                    )
                ]
            )

        # Future: NOT IN, NOT BETWEEN, etc.
        raise NotImplementedError(f"Unsupported NOT expression: {type(inner)}")

    # ------------------------
    # Generic binary operators
    # ------------------------
    BINARY_OPS = {
        exp.EQ: "=",
        exp.GT: ">",
        exp.LT: "<",
        exp.GTE: ">=",
        exp.LTE: "<=",
    }

    for op_type, op_name in BINARY_OPS.items():
        if isinstance(expr, op_type):
            return WhereClause(
                conditions=[
                    Condition(
                        field=expr.left.name,
                        op=op_name,
                        value=_get_value(expr.right),
                    )
                ]
            )

    # ------------------------
    # IN operator
    # ------------------------
    if isinstance(expr, exp.In):
        return WhereClause(
            conditions=[
                Condition(
                    field=expr.this.name,
                    op="in",
                    value=[_get_value(v) for v in expr.expressions],
                )
            ]
        )

    # ------------------------
    # LIKE operator
    # ------------------------
    if isinstance(expr, exp.Like):
        return WhereClause(
            conditions=[
                Condition(
                    field=expr.this.name,
                    op="like",
                    value=_get_value(expr.expression),
                )
            ]
        )

    # ------------------------
    # Fallback
    # ------------------------
    raise NotImplementedError(f"Unsupported expression: {type(expr)}")

def _get_value(node):
    if hasattr(node, "name"):
        return node.name
    return node.this

def definition_to_where(definition_query: str):
    parsed = sqlglot.parse_one(definition_query)
    #return sqlglot_to_where(parsed)
    return _convert(parsed)
