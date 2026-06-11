from typing import Optional, List, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import re

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


def parse_condition(clause: str) -> dict:
    ''' Parse clause into operator, field, value

    '''
    # Thanks AI

    clause = clause.strip()

    # NOT LIKE
    m = re.match(r"(\w+)\s+NOT\s+LIKE\s+'([^']+)'", clause, re.I)
    if m:
        return {
            "field": m.group(1),
            "op": "not_like",
            "value": m.group(2),
        }

    # LIKE
    m = re.match(r"(\w+)\s+LIKE\s+'([^']+)'", clause, re.I)
    if m:
        return {
            "field": m.group(1),
            "op": "like",
            "value": m.group(2),
        }

    # IN
    m = re.match(r"(\w+)\s+IN\s*\(([^)]+)\)", clause, re.I)
    if m:
        values = [v.strip().strip("'") for v in m.group(2).split(",")]
        return {
            "field": m.group(1),
            "op": "in",
            "value": values,
        }

    # NOT EQUAL
    m = re.match(r"(\w+)\s*(<>|!=)\s*'([^']+)'", clause, re.I)
    if m:
        return {
            "field": m.group(1),
            "op": "!=",
            "value": m.group(3),
        }

    # EQUAL
    m = re.match(r"(\w+)\s*=\s*'([^']+)'", clause, re.I)
    if m:
        return {
            "field": m.group(1),
            "op": "=",
            "value": m.group(2),
        }

    # IS NULL
    m = re.match(r"(\w+)\s+IS\s+NULL", clause, re.I)
    if m:
        return {
            "field": m.group(1),
            "op": "is_null",
        }

    # IS NOT NULL
    m = re.match(r"(\w+)\s+IS\s+NOT\s+NULL", clause, re.I)
    if m:
        return {
            "field": m.group(1),
            "op": "is_not_null",
        }

    raise ValueError(f"Unsupported clause: {clause}")


def definition_to_where(definition_query: str):
    sql = normalize(definition_query)

    logic, clauses = split_clauses(sql)

    parsed = [parse_condition(c) for c in clauses]

    # no AND/OR → simple list
    if not logic:
        return parsed

    return {
        logic: parsed
    }