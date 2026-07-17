"""Integration tests for submit_scores. Requires a local MongoDB (see db.py)."""

import pytest

from tools import ValidationError, submit_scores
from db import get_db


@pytest.fixture
def db():
    return get_db()


@pytest.fixture
def ctx():
    return {
        "resume": {
            "HEADER": "Bharath Ganesh | Seattle, WA | bharath@email.com",
            "SKILLS": "Java, Go, Python, JavaScript, TypeScript, SQL, Bash",
            "EXPERIENCE": "Website Administrator, Urbana IL, Jun 2025-May 2026",
        },
        "jd": {
            "job_title": "Backend Engineer (Django)",
            "minimum_requirements": "3+ yrs backend development. Python. Django. PostgreSQL. REST API design.",
            "preferred_qualifications": "Docker, AWS, CI/CD experience. Prior startup experience.",
            "other_information": "Hybrid, 2 days in office. Taipei. Competitive salary and equity.",
        },
    }


@pytest.fixture
def pairs(ctx):
    result = []
    for r_name, r_score_base in [("SKILLS", 6.0), ("EXPERIENCE", 4.0)]:
        for j_name in ctx["jd"]:
            result.append({
                "resume_section_name": r_name,
                "jd_section_name": j_name,
                "resume_section_content": ctx["resume"][r_name],
                "jd_section_content": ctx["jd"][j_name],
                "matching_score": r_score_base + (0.5 if j_name == "minimum_requirements" else 0),
                "rationale": f"{r_name} vs {j_name}: partial overlap on backend-relevant skills.",
            })
    return result


@pytest.fixture
def skipped_sections(ctx):
    return [{
        "document": "resume",
        "section_name": "HEADER",
        "section_content": ctx["resume"]["HEADER"],
        "reason": "Contact info only, no evaluable content.",
    }]


@pytest.fixture(autouse=True)
def cleanup(db):
    yield
    db.annotations.delete_many({"resume_id": {"$regex": "^test_resume_"}})


def test_happy_path(db, ctx, pairs, skipped_sections):
    result = submit_scores(ctx, db, "test_resume_001", "test_jd_001", skipped_sections, pairs)

    assert result["overall_score"] == 5.5
    assert result["pairs_stored"] == len(pairs)
    assert ctx["submit_scores_result"] == result

    stored = list(db.annotations.find({"resume_id": "test_resume_001", "jd_id": "test_jd_001"}))
    assert len(stored) == len(pairs)


def test_resubmit_upserts_not_duplicates(db, ctx, pairs, skipped_sections):
    submit_scores(ctx, db, "test_resume_001", "test_jd_001", skipped_sections, pairs)
    before = db.annotations.count_documents({"resume_id": "test_resume_001", "jd_id": "test_jd_001"})

    submit_scores(ctx, db, "test_resume_001", "test_jd_001", skipped_sections, pairs)
    after = db.annotations.count_documents({"resume_id": "test_resume_001", "jd_id": "test_jd_001"})

    assert before == after == len(pairs)


def test_hallucinated_section_rejected_and_writes_nothing(db, ctx, pairs):
    bad_pairs = [dict(pairs[0])]
    bad_pairs[0]["resume_section_name"] = "NOT_A_REAL_SECTION"

    with pytest.raises(ValidationError):
        submit_scores(ctx, db, "test_resume_002", "test_jd_002", [], bad_pairs)

    assert db.annotations.count_documents({"resume_id": "test_resume_002"}) == 0


def test_incomplete_coverage_rejected(db, ctx, pairs):
    # HEADER is never mentioned in pairs or skipped_sections here.
    with pytest.raises(ValidationError):
        submit_scores(ctx, db, "test_resume_003", "test_jd_003", [], pairs)
