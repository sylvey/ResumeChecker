
import json
import os
import sys

import anthropic
from dotenv import load_dotenv
from tools import dispatch, TOOLS, new_ctx, ValidationError
from Parsing.Parsing import ParseError
from db import get_db




MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
# submit_scores repeats every section's full text across every pair, so the
# final tool call is large. 8000 truncates it mid-call; give it real room.
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "16000"))

SYSTEM_PROMPT = """You are the scoring engine for ResumeChecker. You receive one resume and one job description, and you produce matching scores between every resume section and every JD section.
 
You never see the raw documents directly -- the tools are your only access to them:
- parse_resume(pdf_path) returns the resume split into sections, with headings verbatim. Each section is a dict with "heading" and "content" keys.
- parse_jd(jd_text) returns the JD split into 4 sections: job_title, minimum_requirements, preferred_qualifications, other_information.
 
Workflow, in order:
1. Call parse_resume and parse_jd. Do not score anything before both have returned.
2. Read all sections carefully. Score all resume-section x JD-section pairs yourself. This judgment is yours to make -- no tool does it for you.
3. Call submit_scores exactly once, with all pairs, each carrying the section text you scored, your score, and a one-sentence rationale.
4. Report the overall score that submit_scores returns, plus a brief read on where the candidate is strong and where the gaps are. Do not compute the overall score yourself -- read it back from the tool result.
 
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


def run_agent_turn(client, db, ctx, messages: list) -> str:
    """Runs one user turn to completion: repeatedly calls the model, executing
    any tool calls, until it produces a final text response. Mutates
    `messages` in place so history persists across turns."""

    
    while True:
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
