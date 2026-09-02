"""Exports the annotations collection (resume-section x JD-section pairs,
scored 0-10 by the agent) into sentence-transformers-style JSONL train/val
splits -- the training data db.py's own docstring says this collection
exists to produce, which nothing has turned into a usable dataset until now.

Usage:
    python3 export_annotations.py [--output-dir DIR] [--val-ratio 0.1] [--seed 42]
"""

import argparse
import json
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db  # noqa: E402

load_dotenv()

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data"


def to_example(doc: dict) -> dict:
    """One annotations document -> one sentence-transformers training example.
    matching_score is stored 0-10; normalized to 0-1 to match what
    CosineSimilarityLoss (and most embedding-training setups) expect.
    """
    return {
        "resume_text": doc["resume_section_content"],
        "jd_text": doc["jd_section_content"],
        "score": round(doc["matching_score"] / 10.0, 4),
        "resume_id": doc["resume_id"],
        "jd_id": doc["jd_id"],
        "resume_section_name": doc["resume_section_name"],
        "jd_section_name": doc["jd_section_name"],
    }


def split_train_val(examples: list, val_ratio: float, seed: int) -> tuple:
    """Shuffles (seeded, for reproducibility) and splits into (train, val).
    Guarantees at least one example stays in train whenever there's more
    than one example total, so a small dataset never ends up all-val.
    """
    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)

    if len(shuffled) < 2:
        return shuffled, []

    val_size = max(1, round(len(shuffled) * val_ratio))
    val_size = min(val_size, len(shuffled) - 1)
    return shuffled[val_size:], shuffled[:val_size]


def write_jsonl(path: Path, examples: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    db = get_db()
    docs = list(db.annotations.find({}))
    if not docs:
        print("No annotations found -- nothing to export.")
        return

    examples = [to_example(d) for d in docs]
    train_examples, val_examples = split_train_val(examples, args.val_ratio, args.seed)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "train.jsonl", train_examples)
    write_jsonl(output_dir / "val.jsonl", val_examples)

    print(
        f"Exported {len(train_examples)} train / {len(val_examples)} val "
        f"examples ({len(docs)} annotations total) to {output_dir}"
    )


if __name__ == "__main__":
    main()
