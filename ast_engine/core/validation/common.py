"""Shared utilities and helpers for validation checks."""

from numbers import Integral


def check_subject_ids(gdf, subject_ids):
    if subject_ids is not None and (
        len(subject_ids) != len(gdf)
        or any(not isinstance(value, str) or not value.strip() for value in subject_ids)
        or len(set(subject_ids)) != len(subject_ids)
    ):
        raise ValueError("Supply one unique, nonempty subject ID per row.")


def checked_unit_id(value: object) -> str | int:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("Unit IDs cannot be blank.")
        return value

    if isinstance(value, Integral) and not isinstance(value, bool):
        return int(value)

    raise ValueError(
        "Unit IDs must be strings or integers, not booleans."
    )


def checked_unit_ids(values) -> tuple[str | int, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("Expected IDs must be a list or tuple.")

    result = tuple(checked_unit_id(value) for value in values)

    if len(set(result)) != len(result):
        raise ValueError("Expected IDs cannot contain duplicates.")

    return result