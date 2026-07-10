from __future__ import annotations
from unittest import result

from ast_engine.core.aoi.models import AOIBuildResult
from ast_engine.core.aoi.exceptions import root_cause


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
    expected_codes: set[str],
) -> None:
    actual_codes = {issue.code for issue in result.validation.issues}

    for code in expected_codes:
        assert code in actual_codes, (
            f"Expected validation issue code '{code}' not found in actual codes: "
            f"{sorted(actual_codes)}."
        )
    for code in actual_codes:
        assert code in expected_codes, (
            f"Unexpected validation issue code '{code}' found in actual codes: "
            f"{sorted(actual_codes)}."
        )


def assert_no_validation_issue_codes(
    result: AOIBuildResult,
    *,
    unexpected_codes: set[str],
) -> None:
    actual_codes = {issue.code for issue in result.validation.issues}

    assert actual_codes.isdisjoint(unexpected_codes), (
        f"Unexpected validation issue codes found: "
        f"{sorted(actual_codes & unexpected_codes)}."
    )