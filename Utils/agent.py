
import json
import os
import sys

import anthropic
from dotenv import load_dotenv

from retail_agent import db
from retail_agent.tools import TOOLS, dispatch

load_dotenv() 

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = f"""You are the scoring engine for ResumeChecker. You receive one resume and one job description, and you produce matching scores between every resume section and every JD section.

You never see raw documents directly. Use the tools to parse them first:
- parse_resume(pdf_path) returns the resume split into 4 sections: EDUCATION, EXPERIENCE, PROJECTS, SKILLS.
- parse_jd(jd_text) returns the JD split into 4 sections: job_title, minimum_requirements, preferred_qualifications, other_information.

Workflow (follow in order):
1. Call parse_resume and parse_jd. Do not attempt to score anything before both have returned.
2. Read all 8 sections carefully. Score all 16 resume-section x JD-section pairs yourself — this judgment is yours to make, not a tool's.
3. Call submit_scores exactly once with all 16 scores and a one-sentence rationale for each.

Scoring scale (1.0 to 10.0, one decimal allowed):
- 9-10: directly and strongly relevant; clear evidence the resume section satisfies what the JD section asks for.
- 7-8: solid relevance with good overlap.
- 5-6: partial or adjacent relevance. IMPORTANT: if the candidate has the SAME job ROLE but a DIFFERENT tech stack (e.g. a full-stack developer with Spring experience against a role demanding Django or .NET), score 5-6, NOT low. Transferable role experience and skills still count for a lot.
- 3-4: weak or tangential relevance.
- 1-2: essentially unrelated.

Never score 0, and never score a same-role/different-stack pair as 1-2. A mismatched stack within the same role family is a 5-6.

How to read each pair:
- Against job_title: how well does this resume section fit that role?
- Against minimum_requirements / preferred_qualifications: how well does this resume section satisfy those specific requirements?
- Against other_information: usually lower-signal (logistics, company blurb, benefits) unless it states real requirements. Score what's actually there — don't inflate.

Judge each pair on the actual content returned by the tools. If a section came back empty, score its pairs low (1-2) and say so in the rationale. Base every score on evidence present in the text, not on assumptions about the candidate.

Each rationale must be one sentence, concrete, and cite what in the resume section did or didn't line up with the JD section. These rationales become training data, so make them specific — "no overlap" is useless, "backend experience is Spring/Java while the role requires Django/Python" is useful.

Score every pair independently. Low scores are as valuable as high ones — do not avoid low scores to be generous, and do not compress everything toward the middle.
"""


def run_agent_turn(client, conn, messages: list) -> str:
    """Runs one user turn to completion: repeatedly calls the model, executing
    any tool calls, until it produces a final text response. Mutates
    `messages` in place so history persists across turns."""
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
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
                result = dispatch(conn, block.name, block.input)
                content = json.dumps(result, default=str)
                is_error = False
            except db.BusinessError as e:
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
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY (or put it in .env)", file=sys.stderr)
        sys.exit(1)

    resume_pdf = sys.argv[1]
    jd_path    = sys.argv[2]
    jd_text    = open(jd_path).read()

    client = anthropic.Anthropic()
    messages = [{
        "role": "user",
        "content": (
            f"Score this resume against this job description.\n\n"
            f"Resume PDF path: {resume_pdf}\n\n"
            f"Job description text:\n{jd_text}"
        )
    }]
    reply = run_agent_turn(client, messages)
    print(reply)


if __name__ == "__main__":
    main()
