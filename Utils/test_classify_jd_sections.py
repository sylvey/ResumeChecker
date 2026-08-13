"""Unit tests for classify_jd_sections. Pure function over ctx -- no
database required.
"""

import pytest

from tools import ValidationError, classify_jd_sections, new_ctx


@pytest.fixture
def ctx():
    ctx = new_ctx()
    ctx["jd_raw_sections"] = {
        "Your Core Responsibilities": "Work on meaningful projects.\nParticipate in training.",
        "Your Skills and Experience": "Strong knowledge of algorithms and data structures is required.",
        "Base Salary: $200,000": "",
    }
    return ctx


SECTION_LABELS = [
    {"heading": "Your Core Responsibilities", "category": "minimum_requirements"},
    {"heading": "Your Skills and Experience", "category": "minimum_requirements"},
    {"heading": "Base Salary: $200,000", "category": "other_information"},
]


def test_happy_path_builds_ctx_jd(ctx):
    classify_jd_sections(ctx, job_title="Software Engineer Intern", section_labels=SECTION_LABELS)

    assert ctx["jd"]["job_title"] == "Software Engineer Intern"
    assert "Work on meaningful projects." in ctx["jd"]["minimum_requirements"]
    assert "Strong knowledge" in ctx["jd"]["minimum_requirements"]
    assert ctx["jd"]["preferred_qualifications"] == ""


def test_heading_with_empty_content_is_not_dropped(ctx):
    # Regression test: a heading like "Base Salary: $200,000" with nothing
    # beneath it must still contribute its own text, not vanish.
    classify_jd_sections(ctx, job_title="Software Engineer Intern", section_labels=SECTION_LABELS)
    assert "$200,000" in ctx["jd"]["other_information"]


def test_missing_section_rejected(ctx):
    with pytest.raises(ValidationError):
        classify_jd_sections(
            ctx,
            job_title="Software Engineer Intern",
            section_labels=[{"heading": "Your Core Responsibilities", "category": "minimum_requirements"}],
        )


def test_unknown_heading_rejected(ctx):
    with pytest.raises(ValidationError):
        classify_jd_sections(
            ctx,
            job_title="x",
            section_labels=[{"heading": "Not A Real Section", "category": "other_information"}],
        )


def test_duplicate_heading_rejected(ctx):
    with pytest.raises(ValidationError):
        classify_jd_sections(
            ctx,
            job_title="x",
            section_labels=SECTION_LABELS + [SECTION_LABELS[0]],
        )


def test_invalid_category_rejected(ctx):
    with pytest.raises(ValidationError):
        classify_jd_sections(
            ctx,
            job_title="x",
            section_labels=[{"heading": "Your Core Responsibilities", "category": "job_title"}],
        )


def test_called_before_parse_jd_rejected():
    ctx = new_ctx()
    with pytest.raises(ValidationError):
        classify_jd_sections(ctx, job_title="x", section_labels=[])


def test_called_twice_rejected(ctx):
    classify_jd_sections(ctx, job_title="x", section_labels=SECTION_LABELS)
    with pytest.raises(ValidationError):
        classify_jd_sections(ctx, job_title="x", section_labels=SECTION_LABELS)
