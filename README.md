# PaReJob

An AI agent that matches resumes against job descriptions, built on top of Anthropic's tool-use SDK. It parses a resume and a JD, scores their fit section-by-section, and produces training data for a fine-tuned embedding model.

**Live demo:** [https://parejob.com/](https://parejob.com/)

## Overview

ResumeChecker started as a batch LLM-scoring pipeline for generating training data, then evolved into a multi-step AI agent that scores resumes against job descriptions in real time — with usage data accumulating organically as training signal for the next iteration.

The long-term goal is to fine-tune `BAAI/bge-base-en-v1.5` with contrastive metric learning (`MultipleNegativesRankingLoss`) on (resume, JD) pairs, using this real-world data as both positive and hard-negative examples.

## How it works

The agent uses Anthropic's tool-use SDK with three tools:

- **`parse_resume`** — extracts structured sections from a resume PDF (multi-signal detection: position, font size, bold, all-caps, bullet exclusion, horizontal rules)
- **`parse_jd`** — extracts structured fields from a pasted job description
- **`submit_scores`** — schema-enforced scoring output; computes an overall score via max-per-resume-section, then averaged

Each (resume, JD) pair — including low-scoring ones — is stored in MongoDB to build a labeled dataset for contrastive learning, alongside a separate collection of unscorable sections for future classifier training.

## Tech stack

| Layer       | Tech                                                                  |
| ----------- | --------------------------------------------------------------------- |
| Agent / ML  | Python, Anthropic tool-use SDK, `pdfplumber`, `sentence-transformers` |
| Backend API | Go (Gin)                                                              |
| Frontend    | React, Vite                                                           |
| Storage     | MongoDB (`pymongo`)                                                   |

## Architecture notes

- Parsing logic runs independently of scoring, with a stub `scoring.py` interface so the two workstreams can be developed and tested in parallel
- Per-task context is passed explicitly through a `ctx` dict rather than relying on module-level state
- Resume section names are preserved verbatim (not normalized) to avoid losing signal before classification

## Status

Actively developed. Currently focused on integrating the scoring pipeline and accumulating real usage data toward a held-out human-labeled evaluation set (target: 100–200 pairs) ahead of the first embedding fine-tune.

## Try it

👉 [parejob.com](https://parejob.com/)
