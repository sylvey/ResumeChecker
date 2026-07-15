
"""
The tool/action layer the ResumeChecker agent exposes to the LLM.
 
Design principles:
- Tools cover the mechanical work only: parsing (deterministic) and recording
  the result (format enforcement + storage). The scoring judgment itself is
  NOT a tool -- Claude reads the parsed sections and scores them, and the
  submit_scores schema is what forces that judgment into a fixed shape.
- Order is enforced structurally, not by asking nicely. submit_scores requires
  the actual section text for every pair, so Claude cannot call it without
  having called parse_resume and parse_jd first -- it would have nothing to
  put in those fields.
- Every tool validates and raises ParseError / ValidationError, which the
  caller turns into a tool_result with is_error=True so the model sees it and
  can recover (report a bad PDF, re-parse, etc.) rather than the process
  crashing.
- Only submit_scores touches the database. The parse tools are pure functions
  over a file path / a string and get no db handle.
 
Scoring vs. overall score:
- Every pair is persisted, high scores AND low scores. The low ones are the
  negative examples contrastive training needs.
- Pair count is dynamic (n_resume x n_jd) -- resume section names are not
  normalized, so they can't be an enum and _validate checks them against ctx.
- The overall score = max per resume section, then averaged over sections.
"""
 
from datetime import datetime, timezone
from Parsing.Parsing import JD_SECTIONS, ParseError, parse_jd, parse_resume
 
 

 
 
class ValidationError(Exception):
    """Raised when the model submits scores that don't satisfy the contract."""

def new_ctx() -> dict:
   
    return {"resume": None, "jd": None}


def _parse_resume_tool(ctx, pdf_path: str) -> dict:
    result = parse_resume(pdf_path)
    ctx["resume"] = {s["heading"]: s["content"] for s in result["sections"]}
    return result


def _parse_jd_tool(ctx, jd_text: str, job_title: str) -> dict:
    result = parse_jd(jd_text, job_title)
    ctx["jd"] = dict(result)
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
                "job_title": {
                    "type": "string",
                    "description": (
                        "Split a job description into its four sections: job_title, "
                        "minimum_requirements, preferred_qualifications, other_information. Call this "
                        "before scoring. jd_text is often pasted straight from a job page, so it can "
                        "contain navigation links, buttons, and company boilerplate mixed in with the "
                        "actual posting -- you read it and pass the real role title as job_title. "
                        "other_information holds whatever didn't belong to the requirement sections "
                        "(company blurb, logistics, benefits, and any page junk) -- it is often "
                        "low-signal, so score it for what is actually there rather than inflating it."
                    ),
                },
            },
            "required": ["jd_text", "job_title"],
        },
    },
    {
        "name": "submit_scores",
        "description": (
            "Submit your scores in one call, after both parse tools have returned and you "
            "have judged every pair yourself.\n\n"
            "First decide which sections are scorable. A section is UNSCORABLE only if it "
            "has no real content: empty, a heading with nothing beneath it, or pure "
            "formatting residue. Judge each section on its own, never against the other "
            "document -- 'irrelevant to this job' is a score, not a skip. Thin but real "
            "content IS scorable: a Skills section listing three technologies is weak "
            "evidence, not absent evidence, and belongs in `pairs` where it will score low. "
            "Be strict -- if a section says anything at all about the candidate or the job, "
            "it is scorable.\n\n"
            "List unscorable sections in `skipped_sections`. List every combination of the "
            "remaining resume sections and JD sections in `pairs`, each exactly once, with "
            "the section text you scored copied from the parse results, your score, and a "
            "one-sentence rationale. Never omit a pair because it scores low: low scores are "
            "as valuable as high ones and must be submitted. This tool computes the "
            "user-facing overall score and stores everything; it does not re-judge you."
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
                "skipped_sections": {
                    "type": "array",
                    "description": (
                        "Sections excluded from pairing for having no real content. Pass an "
                        "empty array if every section is scorable."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "document": {
                                "type": "string",
                                "enum": ["resume", "jd"],
                            },
                            "section_name": {
                                "type": "string",
                                "description": "The section name, exactly as the parser returned it.",
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
                        "required": ["document", "section_name", "section_content", "reason"],
                    },
                },
                "pairs": {
                    "type": "array",
                    "description": (
                        "Every combination of scorable resume sections x scorable JD "
                        "sections, each exactly once."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "resume_section_name": {
                                "type": "string",
                                "description": "Resume section name, exactly as parse_resume returned it.",
                            },
                            "jd_section_name": {
                                "type": "string",
                                "enum": JD_SECTIONS,
                            },
                            "resume_section_content": {
                                "type": "string",
                                "description": "The resume section text you scored, as returned by parse_resume.",
                            },
                            "jd_section_content": {
                                "type": "string",
                                "description": "The JD section text you scored, as returned by parse_jd.",
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
                            "jd_section_name",
                            "resume_section_content",
                            "jd_section_content",
                            "matching_score",
                            "rationale",
                        ],
                    },
                },
            },
            "required": ["resume_id", "jd_id", "skipped_sections", "pairs"],
        },
    },
]

def dispatch(ctx, db, name, tool_input):
    tool_input = dict(tool_input)
    fn = {
        "parse_resume": lambda: _parse_resume_tool(ctx, **tool_input),
        "parse_jd": lambda: _parse_jd_tool(ctx, **tool_input),
        "submit_scores": lambda: submit_scores(ctx, db, **tool_input),
    }.get(name)
    if fn is None:
        raise ValidationError(f"Unknown tool '{name}'.")
    return fn()