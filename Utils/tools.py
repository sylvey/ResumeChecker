
"""
The tool/action layer the ResumeChecker agent exposes to the LLM.
 
Design principles:
- Tools cover the mechanical work only: parsing (deterministic) and recording
  the result (format enforcement + storage). The scoring judgment itself is
  NOT a tool -- Claude reads the parsed sections and scores them, and the
  submit_jd_section_scores schema is what forces that judgment into a fixed
  shape.
- Order is enforced structurally, not by asking nicely. submit_jd_section_scores
  requires the actual section text for every pair, so Claude cannot call it
  without having called parse_resume and parse_jd first -- it would have
  nothing to put in those fields.
- Every tool validates and raises ParseError / ValidationError, which the
  caller turns into a tool_result with is_error=True so the model sees it and
  can recover (report a bad PDF, re-parse, etc.) rather than the process
  crashing.
- Only submit_jd_section_scores touches the database. The parse tools are
  pure functions over a file path / a string and get no db handle.
 
Scoring vs. overall score:
- Every pair is persisted, high scores AND low scores. The low ones are the
  negative examples contrastive training needs.
- Pair count is dynamic (n_resume x n_jd) -- resume section names are not
  normalized, so they can't be an enum and _validate checks them against ctx.
- submit_jd_section_scores is called once per JD section (job_title, then
  minimum_requirements, preferred_qualifications, other_information) so
  progress is observable via on_progress as each one lands, instead of
  arriving all at once in a single call at the end.
- The overall score = max per resume section, then averaged over sections,
  computed once every JD section has been submitted.
"""
 
from collections import defaultdict
from datetime import datetime, timezone
from Parsing.Parsing import JD_SECTIONS, ParseError, parse_jd, parse_resume
 
 

 
 
class ValidationError(Exception):
    """Raised when the model submits scores that don't satisfy the contract."""

def new_ctx() -> dict:

    return {
        "resume": None,
        "jd": None,
        # Populated by submit_jd_section_scores as it goes, so completion
        # (and the final overall score) can be detected automatically once
        # every JD section -- a fixed, known-size list -- is accounted for.
        "skipped_resume_sections": None,
        "jd_sections_done": {},
        "all_pairs": [],
    }


def _parse_resume_tool(ctx, pdf_path: str) -> dict:
    result = parse_resume(pdf_path)
    ctx["resume"] = {s["heading"]: s["content"] for s in result["sections"]}
    return result


def _parse_jd_tool(ctx, jd_text: str) -> dict:
    result = parse_jd(jd_text)
    ctx["jd"] = dict(result)
    return result

def submit_jd_section_scores(
    ctx, db, resume_id, jd_id, jd_section_name,
    jd_section_skipped=False, skipped_resume_sections=None, pairs=None,
) -> dict:
    """Validate and persist one JD section's worth of scores, then either
    acknowledge progress or -- once every JD section has been submitted --
    return the final overall score.

    Call once per JD section (JD_SECTIONS is a fixed-length list, so
    completion is detected automatically once every section is accounted
    for -- no separate "finish" call is needed). The model is expected to
    have judged every pair itself; this function only validates the schema
    and stores the result.
    """
    if ctx["resume"] is None or ctx["jd"] is None:
        raise ValidationError("parse_resume and parse_jd must be called before submit_jd_section_scores.")

    if jd_section_name not in ctx["jd"]:
        raise ValidationError(f"Unknown JD section '{jd_section_name}'.")
    if jd_section_name in ctx["jd_sections_done"]:
        raise ValidationError(f"JD section '{jd_section_name}' was already submitted.")

    pairs = pairs or []

    # Resume-section skippability is a property of the section itself, not
    # of which JD section it's being compared against -- so it's only
    # declared once, on the first call, and reused for every call after.
    if ctx["skipped_resume_sections"] is None:
        skipped_resume_sections = skipped_resume_sections or []
        for s in skipped_resume_sections:
            name = s["section_name"]
            if name not in ctx["resume"]:
                raise ValidationError(f"Unknown resume section '{name}' in skipped_resume_sections.")
        ctx["skipped_resume_sections"] = {s["section_name"] for s in skipped_resume_sections}

    scorable_resume_sections = set(ctx["resume"].keys()) - ctx["skipped_resume_sections"]

    if jd_section_skipped:
        if pairs:
            raise ValidationError(f"JD section '{jd_section_name}' marked skipped but pairs were submitted.")
    else:
        for p in pairs:
            r_name = p["resume_section_name"]
            if r_name not in ctx["resume"]:
                raise ValidationError(f"Unknown resume section '{r_name}' in pairs.")
            if r_name in ctx["skipped_resume_sections"]:
                raise ValidationError(f"Resume section '{r_name}' was marked skipped but has a score.")

        covered = {p["resume_section_name"] for p in pairs}
        missing = scorable_resume_sections - covered
        if missing:
            raise ValidationError(f"Resume sections not scored against '{jd_section_name}': {sorted(missing)}")
        extra = covered - scorable_resume_sections
        if extra:
            raise ValidationError(f"Unexpected resume sections scored against '{jd_section_name}': {sorted(extra)}")

    # Persist this batch immediately -- partial results are visible to
    # anyone querying MongoDB even before the whole submission finishes.
    now = datetime.now(timezone.utc)
    for p in pairs:
        db.annotations.update_one(
            {
                "resume_id": resume_id,
                "jd_id": jd_id,
                "resume_section_name": p["resume_section_name"],
                "jd_section_name": jd_section_name,
            },
            {
                "$set": {
                    "resume_section_name": p["resume_section_name"],
                    "jd_section_name": jd_section_name,
                    "resume_section_content": p["resume_section_content"],
                    "jd_section_content": ctx["jd"][jd_section_name],
                    "matching_score": p["matching_score"],
                    "rationale": p["rationale"],
                    "source": "llm",
                    "created_at": now,
                }
            },
            upsert=True,
        )
        ctx["all_pairs"].append({**p, "jd_section_name": jd_section_name})

    ctx["jd_sections_done"][jd_section_name] = True

    remaining = [s for s in ctx["jd"].keys() if s not in ctx["jd_sections_done"]]
    if remaining:
        return {
            "status": "in_progress",
            "jd_section_name": jd_section_name,
            "pairs_stored": len(pairs),
            "remaining_jd_sections": remaining,
        }

    # Every JD section is accounted for -- compute the final overall score:
    # max per resume section, then average over sections.
    by_section = defaultdict(list)
    for pair in ctx["all_pairs"]:
        by_section[pair["resume_section_name"]].append(pair["matching_score"])
    section_maxes = [max(scores) for scores in by_section.values()]
    overall_score = sum(section_maxes) / len(section_maxes) if section_maxes else 0.0

    result = {
        "resume_id": resume_id,
        "jd_id": jd_id,
        "overall_score": overall_score,
        "pairs_stored": len(ctx["all_pairs"]),
    }
    ctx["submit_scores_result"] = result
    return result

TOOLS = [
    {
        "name": "parse_resume",
        "description": (
            "Read a resume PDF from disk and split it into sections, each with the heading "
            "exactly as it appears in the resume. Call this first -- you have no other way "
            "to see the resume, and you must not score anything until it returns. Section "
            "names are NOT normalized: whatever the resume calls a section is what you score "
            "and what gets stored, so use the headings verbatim and do not rename, merge, or "
            "translate them. Expect unanticipated sections (Publications, Certifications, "
            "Awards, Languages) and treat them as first-class -- they carry real signal for "
            "some roles. HEADER is the text above the first heading (name, contact details, "
            "and often an objective or target job title); score it like any other section."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Filesystem path to the resume PDF.",
                },
            },
            "required": ["pdf_path"],
        },
    },
    {
        "name": "parse_jd",
        "description": (
            "Split a job description into its four sections: job_title, "
            "minimum_requirements, preferred_qualifications, other_information. Call this "
            "before scoring. other_information holds whatever didn't belong to the "
            "requirement sections (company blurb, logistics, benefits) -- it is often "
            "low-signal, so score it for what is actually there rather than inflating it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jd_text": {
                    "type": "string",
                    "description": "Raw job description text.",
                },
            },
            "required": ["jd_text"],
        },
    },
    {
        "name": "submit_jd_section_scores",
        "description": (
            "Submit scores for ONE JD section against every scorable resume section. "
            "Call this once per JD section -- job_title, then minimum_requirements, then "
            "preferred_qualifications, then other_information, in that order -- only after "
            "both parse tools have returned and you have judged every resume section "
            "against the current JD section yourself.\n\n"
            "On your FIRST call only, also decide which resume sections are unscorable "
            "and list them in `skipped_resume_sections` -- this applies to the resume as a "
            "whole, not to any one JD section, so do not repeat or revise it on later "
            "calls. A resume section is UNSCORABLE only if it has no real content: empty, "
            "a heading with nothing beneath it, or pure formatting residue. Judge it on "
            "its own, never against the JD -- 'irrelevant to this job' is a score, not a "
            "skip. Thin but real content IS scorable: a Skills section listing three "
            "technologies is weak evidence, not absent evidence, and belongs in `pairs` "
            "where it will score low.\n\n"
            "If the CURRENT JD section itself has no real content, set "
            "`jd_section_skipped` to true and leave `pairs` empty for this call.\n\n"
            "Otherwise, list every scorable resume section in `pairs`, each exactly once, "
            "with the section text you scored copied from the parse results, your score, "
            "and a one-sentence rationale. Never omit a pair because it scores low: low "
            "scores are as valuable as high ones and must be submitted. This tool stores "
            "everything and, once every JD section has been submitted, computes and "
            "returns the final overall score -- it does not re-judge you."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resume_id": {
                    "type": "string",
                    "description": "Identifier for this resume (e.g. the PDF filename).",
                },
                "jd_id": {
                    "type": "string",
                    "description": "Identifier for this job description.",
                },
                "jd_section_name": {
                    "type": "string",
                    "enum": JD_SECTIONS,
                    "description": "Which JD section this call's scores are for.",
                },
                "jd_section_skipped": {
                    "type": "boolean",
                    "description": (
                        "True if this JD section has no real content to score against. "
                        "Defaults to false."
                    ),
                },
                "skipped_resume_sections": {
                    "type": "array",
                    "description": (
                        "Resume sections with no real content, excluded from all pairing. "
                        "Only meaningful on your first call -- pass an empty array if every "
                        "resume section is scorable."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_name": {
                                "type": "string",
                                "description": "The resume section name, exactly as parse_resume returned it.",
                            },
                            "section_content": {
                                "type": "string",
                                "description": "Whatever content the section did have (often empty).",
                            },
                            "reason": {
                                "type": "string",
                                "description": (
                                    "Why there is nothing to score, e.g. 'heading present "
                                    "but no content beneath it'."
                                ),
                            },
                        },
                        "required": ["section_name", "section_content", "reason"],
                    },
                },
                "pairs": {
                    "type": "array",
                    "description": (
                        "Every scorable resume section, scored against the current JD "
                        "section, each exactly once. Leave empty if jd_section_skipped is "
                        "true."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "resume_section_name": {
                                "type": "string",
                                "description": "Resume section name, exactly as parse_resume returned it.",
                            },
                            "resume_section_content": {
                                "type": "string",
                                "description": "The resume section text you scored, as returned by parse_resume.",
                            },
                            "matching_score": {
                                "type": "number",
                                "description": (
                                    "1.0-10.0, one decimal allowed. Same role but a "
                                    "different tech stack is a 5-6, never a 1-2. Never 0."
                                ),
                            },
                            "rationale": {
                                "type": "string",
                                "description": (
                                    "One concrete sentence naming what did or didn't line "
                                    "up, e.g. 'backend experience is Spring/Java while the "
                                    "role requires Django/Python'. This becomes training "
                                    "data, so 'no overlap' is not acceptable."
                                ),
                            },
                        },
                        "required": [
                            "resume_section_name",
                            "resume_section_content",
                            "matching_score",
                            "rationale",
                        ],
                    },
                },
            },
            "required": ["resume_id", "jd_id", "jd_section_name", "pairs"],
        },
    },
]

def dispatch(ctx, db, name, tool_input):
    tool_input = dict(tool_input)
    fn = {
        "parse_resume": lambda: _parse_resume_tool(ctx, **tool_input),
        "parse_jd": lambda: _parse_jd_tool(ctx, **tool_input),
        "submit_jd_section_scores": lambda: submit_jd_section_scores(ctx, db, **tool_input),
    }.get(name)
    if fn is None:
        raise ValidationError(f"Unknown tool '{name}'.")
    return fn()