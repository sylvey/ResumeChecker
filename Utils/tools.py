
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
- All 16 pairs are persisted, high scores AND low scores. The low ones are the
  negative examples that contrastive training (MultipleNegativesRankingLoss)
  needs -- dropping them would leave nothing to learn "not a match" from.
- The user-facing overall score uses only the best JD match per resume section
  (max over the 4 JD sections, then averaged over the 4 resume sections). That
  is a presentation concern and deliberately separate from what gets stored.
"""
 
from datetime import datetime, timezone
 
RESUME_SECTIONS = ["EDUCATION", "EXPERIENCE", "PROJECTS", "SKILLS"]
JD_SECTIONS = ["job_title", "minimum_requirements",
               "preferred_qualifications", "other_information"]
 
 
class ParseError(Exception):
    """Raised when a document can't be read or split into sections."""
 
 
class ValidationError(Exception):
    """Raised when the model submits scores that don't satisfy the contract."""
 
 
TOOLS = [
    {
        "name": "parse_resume",
        "description": (
            "Read a resume PDF from disk and split it into its four sections: EDUCATION, "
            "EXPERIENCE, PROJECTS, SKILLS. Call this first -- you have no other way to see "
            "the resume, and you must not score anything until it returns. A section that "
            "genuinely isn't present in the resume comes back as an empty string; that is a "
            "real signal about the candidate, not a parsing failure, so score its pairs low "
            "rather than assuming the content exists somewhere."
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
            "before scoring. Sections the JD doesn't state come back as an empty string. "
            "other_information holds whatever didn't belong to the requirement sections "
            "(company blurb, logistics, benefits) -- it is often low-signal, so score it for "
            "what is actually there."
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
        "name": "submit_scores",
        "description": (
            "Submit your scores for all 16 resume-section x JD-section pairs at once. Call "
            "this exactly once, after both parse tools have returned and you have judged "
            "every pair yourself. For each pair you must supply the section text you actually "
            "scored (copied from the parse tool results) along with your score and a "
            "one-sentence rationale -- this is what ties each score to the evidence behind it. "
            "Every pair is recorded, low scores included: low-scoring pairs are as valuable as "
            "high-scoring ones, so score honestly rather than generously. This tool computes "
            "the user-facing overall score and stores the annotations; it does not re-judge "
            "your scores."
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
                "pairs": {
                    "type": "array",
                    "description": (
                        "Exactly 16 entries: every combination of the 4 resume sections and "
                        "the 4 JD sections, each scored independently."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "resume_section_name": {
                                "type": "string",
                                "enum": RESUME_SECTIONS,
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
                                    "1.0-10.0, one decimal allowed. Same role but a different "
                                    "tech stack is a 5-6, never a 1-2. Never 0."
                                ),
                            },
                            "rationale": {
                                "type": "string",
                                "description": (
                                    "One concrete sentence naming what did or didn't line up, "
                                    "e.g. 'backend experience is Spring/Java while the role "
                                    "requires Django/Python'. This becomes training data, so "
                                    "'no overlap' is not acceptable."
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
            "required": ["resume_id", "jd_id", "pairs"],
        },
    },
]

def dispatch(db, name, tool_input):
    """Run one tool call. Returns a JSON-able dict on success. Raises
    ParseError / ValidationError on bad input -- the caller turns that into a
    tool_result with is_error=True so the model sees it and can recover.
 
    Only submit_scores gets `db`; the parse tools are pure.
    """
    tool_input = dict(tool_input)
 
    fn = {
        "parse_resume": lambda: parse_resume(**tool_input),
        "parse_jd": lambda: parse_jd(**tool_input),
        "submit_scores": lambda: submit_scores(db, **tool_input),
    }.get(name)
    if fn is None:
        raise ValidationError(f"Unknown tool '{name}'.")
    return fn()