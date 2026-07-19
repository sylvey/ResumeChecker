"""Flask API wrapping the resume-scoring agent pipeline.

This is a thin HTTP entry point to the same pipeline the CLI in agent.py runs.
It does NO parsing of its own: it saves the uploaded resume and the pasted job
description to temp files, hands the paths to the agent (whose own tools parse
them internally), returns the scores, and deletes the temp files afterwards.

Intended to be called server-to-server by the Go backend, which forwards the
multipart form (`resume_file`, `job_description`) it already receives from the
React frontend.
"""

import os
import tempfile

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from agent import run_agent_turn
from tools import new_ctx
from db import get_db

load_dotenv()

for _var in ("ANTHROPIC_API_KEY", "MONGO_URI"):
    if not os.environ.get(_var):
        raise RuntimeError(f"Set {_var} (or put it in .env)")

app = Flask(__name__)

# Created once and reused across requests. Both are thread-safe, so there's no
# need to reconnect or re-instantiate per request.
client = anthropic.Anthropic()
db = get_db()


@app.post("/score")
def score():
    jd_text = (request.form.get("job_description") or "").strip()
    if not jd_text:
        return jsonify({"error": "job_description field is required"}), 400

    file = request.files.get("resume_file")
    if file is None or file.filename == "":
        return jsonify({"error": "resume_file field is required"}), 400
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "resume_file must be a PDF document"}), 400

    # Save both inputs to temp files; the agent reads the resume PDF from disk.
    resume_fd, resume_path = tempfile.mkstemp(suffix=".pdf")
    os.close(resume_fd)
    jd_fd, jd_path = tempfile.mkstemp(suffix=".txt")
    os.close(jd_fd)

    try:
        file.save(resume_path)
        with open(jd_path, "w", encoding="utf-8") as f:
            f.write(jd_text)

        # Same message the CLI builds in agent.main(), just sourced from HTTP.
        jd_from_file = open(jd_path, encoding="utf-8").read()
        messages = [{
            "role": "user",
            "content": (
                f"Score this resume against this job description.\n\n"
                f"Resume PDF path: {resume_path}\n\n"
                f"Job description text:\n{jd_from_file}"
            )
        }]
        ctx = new_ctx()
        reply = run_agent_turn(client, db, ctx, messages)

        result = ctx.get("submit_scores_result")
        if result is None:
            # The agent finished without calling submit_scores (e.g. an
            # unrecoverable parse error). Surface it instead of crashing.
            return jsonify({
                "error": "Agent did not submit scores",
                "reply": reply,
            }), 502

        pairs = list(db.annotations.find(
            {"resume_id": result["resume_id"], "jd_id": result["jd_id"]},
            {"_id": 0},
        ))
        return jsonify({
            "reply": reply,
            "overall_score": result["overall_score"],
            "pairs_stored": result["pairs_stored"],
            "pairs": pairs,
        })
    finally:
        for path in (resume_path, jd_path):
            try:
                os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    # Port 5001 to avoid the Go server on :8080.
    app.run(host="0.0.0.0", port=5001)
