"""Integration tests for submit_jd_section_scores. Requires a local MongoDB (see db.py)."""

import pytest

from tools import ValidationError, submit_jd_section_scores, new_ctx
from Parsing.Parsing import JD_SECTIONS
from db import get_db


@pytest.fixture
def db():
    return get_db()


@pytest.fixture
def ctx():
    ctx = new_ctx()
    ctx["resume"] = {
        "HEADER": "Bharath Ganesh | Seattle, WA | bharath@email.com",
        "SKILLS": "Java, Go, Python, JavaScript, TypeScript, SQL, Bash",
        "EXPERIENCE": "Website Administrator, Urbana IL, Jun 2025-May 2026",
    }
    ctx["jd"] = {
        "job_title": "Backend Engineer (Django)",
        "minimum_requirements": "3+ yrs backend development. Python. Django. PostgreSQL. REST API design.",
        "preferred_qualifications": "Docker, AWS, CI/CD experience. Prior startup experience.",
        "other_information": "Hybrid, 2 days in office. Taipei. Competitive salary and equity.",
    }
    return ctx


def _pairs_for(ctx, jd_section_name, resume_sections=("SKILLS", "EXPERIENCE")):
    # SKILLS always scores 6.0 and EXPERIENCE always scores 4.0, regardless of
    # jd_section_name, so the expected overall_score (average of per-resume-
    # section maxes) works out to (6.0 + 4.0) / 2 = 5.0 in the happy path.
    return [
        {
            "resume_section_name": r_name,
            "resume_section_content": ctx["resume"][r_name],
            "matching_score": 6.0 if r_name == "SKILLS" else 4.0,
            "rationale": f"{r_name} vs {jd_section_name}: partial overlap on backend-relevant skills.",
        }
        for r_name in resume_sections
    ]


@pytest.fixture
def skipped_resume_sections(ctx):
    return [{
        "section_name": "HEADER",
        "section_content": ctx["resume"]["HEADER"],
        "reason": "Contact info only, no evaluable content.",
    }]


@pytest.fixture(autouse=True)
def cleanup(db):
    yield
    db.annotations.delete_many({"resume_id": {"$regex": "^test_resume_"}})


def _submit_all_sections(ctx, db, resume_id, jd_id, skipped_resume_sections):
    result = None
    for i, section in enumerate(JD_SECTIONS):
        result = submit_jd_section_scores(
            ctx, db, resume_id, jd_id, section,
            skipped_resume_sections=skipped_resume_sections if i == 0 else None,
            pairs=_pairs_for(ctx, section),
        )
    return result


def test_happy_path(db, ctx, skipped_resume_sections):
    result = _submit_all_sections(ctx, db, "test_resume_001", "test_jd_001", skipped_resume_sections)

    assert result["pairs_stored"] == 8  # 2 scorable resume sections x 4 JD sections
    assert result["overall_score"] == pytest.approx(5.0)
    assert ctx["submit_scores_result"] == result

    stored = list(db.annotations.find({"resume_id": "test_resume_001", "jd_id": "test_jd_001"}))
    assert len(stored) == 8


def test_intermediate_calls_report_in_progress(db, ctx, skipped_resume_sections):
    result = submit_jd_section_scores(
        ctx, db, "test_resume_002", "test_jd_002", JD_SECTIONS[0],
        skipped_resume_sections=skipped_resume_sections,
        pairs=_pairs_for(ctx, JD_SECTIONS[0]),
    )
    assert result["status"] == "in_progress"
    assert result["remaining_jd_sections"] == JD_SECTIONS[1:]


def test_db_upsert_not_duplicated_across_runs(db, ctx, skipped_resume_sections):
    _submit_all_sections(ctx, db, "test_resume_003", "test_jd_003", skipped_resume_sections)
    before = db.annotations.count_documents({"resume_id": "test_resume_003", "jd_id": "test_jd_003"})

    # A second, independent run (fresh ctx, same resume_id/jd_id) simulates
    # re-scoring the same pair -- should upsert in place, not duplicate.
    fresh_ctx = new_ctx()
    fresh_ctx["resume"] = ctx["resume"]
    fresh_ctx["jd"] = ctx["jd"]
    _submit_all_sections(fresh_ctx, db, "test_resume_003", "test_jd_003", skipped_resume_sections)
    after = db.annotations.count_documents({"resume_id": "test_resume_003", "jd_id": "test_jd_003"})

    assert before == after == 8


def test_resubmitting_same_section_in_one_run_rejected(db, ctx, skipped_resume_sections):
    submit_jd_section_scores(
        ctx, db, "test_resume_004", "test_jd_004", JD_SECTIONS[0],
        skipped_resume_sections=skipped_resume_sections,
        pairs=_pairs_for(ctx, JD_SECTIONS[0]),
    )
    with pytest.raises(ValidationError):
        submit_jd_section_scores(
            ctx, db, "test_resume_004", "test_jd_004", JD_SECTIONS[0],
            pairs=_pairs_for(ctx, JD_SECTIONS[0]),
        )


def test_hallucinated_resume_section_rejected_and_writes_nothing(db, ctx):
    bad_pairs = _pairs_for(ctx, JD_SECTIONS[0])
    bad_pairs[0]["resume_section_name"] = "NOT_A_REAL_SECTION"

    with pytest.raises(ValidationError):
        submit_jd_section_scores(ctx, db, "test_resume_005", "test_jd_005", JD_SECTIONS[0], pairs=bad_pairs)

    assert db.annotations.count_documents({"resume_id": "test_resume_005"}) == 0


def test_incomplete_coverage_rejected(db, ctx):
    # HEADER is never mentioned in pairs or skipped_resume_sections here.
    incomplete_pairs = [p for p in _pairs_for(ctx, JD_SECTIONS[0]) if p["resume_section_name"] == "SKILLS"]

    with pytest.raises(ValidationError):
        submit_jd_section_scores(ctx, db, "test_resume_006", "test_jd_006", JD_SECTIONS[0], pairs=incomplete_pairs)


def test_unknown_jd_section_rejected(db, ctx):
    with pytest.raises(ValidationError):
        submit_jd_section_scores(ctx, db, "test_resume_007", "test_jd_007", "not_a_real_jd_section", pairs=[])
