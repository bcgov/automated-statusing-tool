from __future__ import annotations
from unittest import result
from collections.abc import Collection

from ast_engine.core.aoi.models import AOIBuildResult


def format_validation_issues(result: AOIBuildResult) -> list[str]:
    return [
        f"{issue.severity.upper()} | {issue.code}: {issue.message}"
        for issue in result.validation.issues
    ]


def assert_successful_aoi_build(
    result: AOIBuildResult,
) -> None:
    """
    Assert the basic AOIBuilder success contract.

    Do not duplicate detailed AOI validation rules here.
    Those belong in validator-specific tests.
    """
    assert result is not None
    assert result.aoi is not None
    assert result.validation is not None
    assert result.normalization_report is not None

    assert result.is_valid, format_validation_issues(result)


def assert_validation_issue_codes(
    result: AOIBuildResult,
    *,
    expected_codes: Collection[str],
) -> None:
    actual = {
        issue.code
        for issue in result.validation.issues
    }
    expected = set(expected_codes)

    assert actual == expected, (
        f"Expected validation codes {sorted(expected)}; "
        f"received {sorted(actual)}."
    )


def assert_no_validation_issue_codes(
    result: AOIBuildResult,
    *,
    unexpected_codes: Collection[str],
) -> None:
    actual_codes = {
        issue.code
        for issue in result.validation.issues
    }
    found = actual_codes.intersection(unexpected_codes)

    assert not found, (
        f"Unexpected validation issue codes found: {sorted(found)}."
    )
    