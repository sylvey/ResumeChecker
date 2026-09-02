"""Unit tests for export_annotations.py's pure logic -- to_example and
split_train_val. No database required; fetch_annotations (the one Mongo-
touching function) is a one-line find({}) wrapper not worth mocking.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ModelTraining"))

from export_annotations import split_train_val, to_example


def make_doc(score, **overrides):
    doc = {
        "resume_id": "r1",
        "jd_id": "j1",
        "resume_section_name": "Experience",
        "jd_section_name": "minimum_requirements",
        "resume_section_content": "Built things.",
        "jd_section_content": "Must build things.",
        "matching_score": score,
    }
    doc.update(overrides)
    return doc


def test_to_example_normalizes_score_to_0_1():
    assert to_example(make_doc(10))["score"] == 1.0
    assert to_example(make_doc(0))["score"] == 0.0
    assert to_example(make_doc(5))["score"] == 0.5
    assert to_example(make_doc(7.5))["score"] == 0.75


def test_to_example_preserves_identifying_fields():
    doc = make_doc(8, resume_id="abc", jd_id="def")
    ex = to_example(doc)
    assert ex["resume_id"] == "abc"
    assert ex["jd_id"] == "def"
    assert ex["resume_section_name"] == "Experience"
    assert ex["jd_section_name"] == "minimum_requirements"
    assert ex["resume_text"] == "Built things."
    assert ex["jd_text"] == "Must build things."


def test_split_train_val_respects_ratio():
    examples = [make_doc(i) for i in range(100)]
    train, val = split_train_val(examples, val_ratio=0.1, seed=42)
    assert len(train) + len(val) == 100
    assert len(val) == 10


def test_split_train_val_is_reproducible_with_same_seed():
    examples = [make_doc(i) for i in range(50)]
    train1, val1 = split_train_val(examples, val_ratio=0.2, seed=7)
    train2, val2 = split_train_val(examples, val_ratio=0.2, seed=7)
    assert train1 == train2
    assert val1 == val2


def test_split_train_val_different_seeds_can_differ():
    examples = [make_doc(i) for i in range(50)]
    _, val_a = split_train_val(examples, val_ratio=0.2, seed=1)
    _, val_b = split_train_val(examples, val_ratio=0.2, seed=2)
    assert val_a != val_b


def test_split_train_val_empty_input():
    train, val = split_train_val([], val_ratio=0.1, seed=42)
    assert train == []
    assert val == []


def test_split_train_val_single_example_stays_in_train():
    examples = [make_doc(9)]
    train, val = split_train_val(examples, val_ratio=0.5, seed=42)
    assert len(train) == 1
    assert val == []


def test_split_train_val_small_set_keeps_at_least_one_in_train():
    # val_ratio=0.9 over 3 examples would naively put all but one in val --
    # confirm train never goes empty when there's more than one example.
    examples = [make_doc(i) for i in range(3)]
    train, val = split_train_val(examples, val_ratio=0.9, seed=42)
    assert len(train) >= 1
    assert len(train) + len(val) == 3


def test_split_train_val_no_overlap_and_no_loss():
    examples = [make_doc(i, resume_id=str(i)) for i in range(37)]
    train, val = split_train_val(examples, val_ratio=0.25, seed=3)
    train_ids = {e["resume_id"] for e in train}
    val_ids = {e["resume_id"] for e in val}
    assert train_ids.isdisjoint(val_ids)
    assert train_ids | val_ids == {str(i) for i in range(37)}
