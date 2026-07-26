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
import threading
import uuid

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

# Scoring takes minutes, so /score kicks off a background thread and returns
# a job_id immediately; the frontend polls /score/<job_id>/status for
# progress. In-memory and per-process -- fine for a single dev server, would
# need a shared store (e.g. Mongo) if this ever runs behind multiple workers.
JOBS = {}
JOBS_LOCK = threading.Lock()

STAGE_LABELS = {
    "parse_resume": "Parsing resume...",
    "parse_jd": "Parsing job description...",
    "submit_scores": "Saving scores...",
    "thinking": "Scoring sections...",
}


def _run_job(job_id, resume_path, jd_path):
    def on_progress(tool_name):
        with JOBS_LOCK:
            JOBS[job_id]["stage"] = STAGE_LABELS.get(tool_name, tool_name)

    try:
        jd_text = open(jd_path, encoding="utf-8").read()
        messages = [{
            "role": "user",
            "content": (
                f"Score this resume against this job description.\n\n"
                f"Resume PDF path: {resume_path}\n\n"
                f"Job description text:\n{jd_text}"
            )
        }]
        ctx = new_ctx()
        reply = run_agent_turn(client, db, ctx, messages, on_progress=on_progress)

        result = ctx.get("submit_scores_result")
        if result is None:
            # The agent finished without calling submit_scores (e.g. an
            # unrecoverable parse error). Surface it instead of crashing.
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "error",
                    "error": "Agent did not submit scores",
                    "reply": reply,
                }
            return

        pairs = list(db.annotations.find(
            {"resume_id": result["resume_id"], "jd_id": result["jd_id"]},
            {"_id": 0},
        ))
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "done",
                "reply": reply,
                "overall_score": result["overall_score"],
                "pairs_stored": result["pairs_stored"],
                "pairs": pairs,
            }
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "error", "error": str(e)}
    finally:
        for path in (resume_path, jd_path):
            try:
                os.remove(path)
            except OSError:
                pass


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
    file.save(resume_path)
    with open(jd_path, "w", encoding="utf-8") as f:
        f.write(jd_text)

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "stage": "Starting..."}

    thread = threading.Thread(target=_run_job, args=(job_id, resume_path, jd_path), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.get("/score/<job_id>/status")
def score_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown job_id"}), 404
    return jsonify(job)


if __name__ == "__main__":
    # Port 5001 to avoid the Go server on :8080. threaded=True lets status
    # polls get served while a scoring job's background thread is running.
    app.run(host="0.0.0.0", port=5001, threaded=True)
