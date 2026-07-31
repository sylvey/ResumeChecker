
import json
import os
import sys

import anthropic
from dotenv import load_dotenv
from tools import dispatch, TOOLS, new_ctx, ValidationError
from Parsing.Parsing import JD_SECTIONS, ParseError
from db import get_db




MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
# Each submit_jd_section_scores call repeats one JD section's worth of pairs,
# so a single call is much smaller than the old one-shot submit_scores was --
# but keep the same generous ceiling since a JD section can still pair
# against many resume sections.
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "16000"))

SYSTEM_PROMPT = """You are the scoring engine for ResumeChecker. You receive one resume and one job description, and you produce matching scores between every resume section and every JD section.
 
You never see the raw documents directly -- the tools are your only access to them:
- parse_resume(pdf_path) returns the resume split into sections, with headings verbatim. Each section is a dict with "heading" and "content" keys.
- parse_jd(jd_text) returns the JD split into 4 sections: job_title, minimum_requirements, preferred_qualifications, other_information.
 
Workflow, in order:
1. Call parse_resume and parse_jd. Do not score anything before both have returned.
2. Read all sections carefully. Decide which resume sections are unscorable (no real content) -- this is a property of the resume, not of any one JD section, so you decide it once.
3. Score resume sections against job_title yourself, then call submit_jd_section_scores for job_title -- on this first call, also pass skipped_resume_sections. This judgment is yours to make -- no tool does it for you.
4. Repeat step 3 for minimum_requirements, then preferred_qualifications, then other_information, in that order -- one submit_jd_section_scores call per JD section, four calls total. If a JD section itself has no real content, set jd_section_skipped=true and leave pairs empty for that call instead of scoring it.
5. The fourth call's result carries the final overall_score. Report that score, plus a brief read on where the candidate is strong and where the gaps are. Do not compute the overall score yourself -- read it back from the tool result.
 
Scoring scale (1.0 to 10.0, one decimal allowed):
- 9-10: directly and strongly relevant; clear evidence the resume section satisfies what the JD section asks for.
- 7-8: solid relevance with good overlap.
- 5-6: partial or adjacent relevance. IMPORTANT: if the candidate has the SAME job ROLE but a DIFFERENT tech stack (e.g. a full-stack developer with Spring experience against a role demanding Django or .NET), score 5-6, NOT low. Transferable role experience counts for a lot.
- 3-4: weak or tangential relevance.
- 1-2: essentially unrelated.
 
Never score 0. Never score a same-role/different-stack pair as 1-2 -- a mismatched stack within the same role family is a 5-6.
 
How to read each pair:
- Against job_title: how well does this resume section fit that role?
- Against minimum_requirements / preferred_qualifications: how well does this resume section satisfy those specific requirements?
- Against other_information: usually low-signal (logistics, company blurb, benefits) unless it states real requirements. Score what is actually there; don't inflate it.
 
Judge every pair on the content the tools returned, not on assumptions about the candidate.

Every rationale must be one concrete sentence naming what did or did not line up -- "backend experience is Spring/Java while the role requires Django/Python" is useful; "no overlap" is not. These rationales are stored as training data.
 
Score each pair independently. Low scores are as valuable as high ones: they are the negative examples the training set needs. Do not be generous, and do not compress everything toward the middle.
 
Keep your final response short and concrete. No preamble."""


def run_agent_turn(client, db, ctx, messages: list, on_progress=None) -> str:
    """Runs one user turn to completion: repeatedly calls the model, executing
    any tool calls, until it produces a final text response. Mutates
    `messages` in place so history persists across turns.

    If given, on_progress(tool_name, tool_input) is called right before each
    tool dispatch, tool_input included so a caller (e.g. a web server) can
    read e.g. which jd_section_name a submit_jd_section_scores call is for --
    a real, observable progress event, not a guess -- without needing to
    inspect the model's traffic itself. It is also called (with tool_input
    as None) right before every model call: "thinking" for the gaps where
    Claude is reasoning with no tool call to hang a more specific label on --
    before parsing, and between submit_jd_section_scores calls while judging
    the next JD section -- and "finishing" for the final call after all four
    JD sections have been submitted, which only writes the closing summary
    and would otherwise misleadingly report "thinking" again for a stage
    that's already done.
    """

    called_tools = []

    while True:
        if on_progress:
            submitted = called_tools.count("submit_jd_section_scores")
            if submitted >= len(JD_SECTIONS):
                on_progress("finishing", None)
            elif "parse_resume" in called_tools and "parse_jd" in called_tools:
                # Parsing is done and JD_SECTIONS is a fixed, known order, so
                # the next JD section can be predicted -- reported here, before
                # Claude has actually reasoned about it, so the label covers
                # the whole reasoning window instead of only appearing once
                # the (already-finished) result is submitted.
                on_progress("thinking", {"jd_section_name": JD_SECTIONS[submitted]})
            else:
                on_progress("thinking", None)
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text").strip()

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if on_progress:
                on_progress(block.name, block.input)
            called_tools.append(block.name)
            try:
                result = dispatch(ctx, db, block.name, block.input)
                content = json.dumps(result, default=str)
                is_error = False
            except (ParseError, ValidationError) as e:
                content = str(e)
                is_error = True
            except Exception as e:
                content = f"Error running {block.name}: {e}"
                is_error = True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": tool_results})


def main():
    load_dotenv() 
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY (or put it in .env)", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("MONGO_URI"):
        print("Set MONGO_URI (or put it in .env)", file=sys.stderr)
        sys.exit(1)

    resume_pdf = sys.argv[1]
    jd_path    = sys.argv[2]
    jd_text    = open(jd_path).read()

    client = anthropic.Anthropic()
    db = get_db()
    messages = [{
        "role": "user",
        "content": (
            f"Score this resume against this job description.\n\n"
            f"Resume PDF path: {resume_pdf}\n\n"
            f"Job description text:\n{jd_text}"
        )
    }]
    ctx = new_ctx()
    reply = run_agent_turn(client, db, ctx, messages)

    print(reply)
    result = ctx.get("submit_scores_result")
    pairs = list(db.annotations.find(
        {"resume_id": result["resume_id"], "jd_id": result["jd_id"]},
        {"_id": 0}
    ))
    output = {
        "overall_score": result["overall_score"],
        "pairs_stored": result["pairs_stored"],
        "pairs": pairs,
    }
    print(json.dumps(output, default=str, indent=2))


if __name__ == "__main__":
    main()
