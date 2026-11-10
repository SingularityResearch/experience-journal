"""Tripwire for the measured thresholds (see AGENTS.md, "Thresholds are measured values").

These numbers were measured on the owner's labeled photos and posed sessions. This test fails when one changes,
so that a change is deliberate: re-measure first (tools/eval_models.py, tools/webcam_eval.py, tools/expr_eval.py,
`python face_id.py people`), then update the number here and in PROJECT_CONTEXT.md in the same commit.
"""
import re
from pathlib import Path

import face_id as F
import labels as L

HERE = Path(__file__).resolve().parents[1]


def test_recognition_thresholds():
    assert {k: (v["match"], v["cluster"]) for k, v in F.REC_MODELS.items()} == {
        "arcface_w600k_r50": (0.35, 0.70), "sface_2021dec": (0.45, 0.58)}
    assert (F.Q_ENROLL, F.Q_EXPR, F.MAX_TURN, F.DET_SCORE, F.MIN_FACE) == (0.30, 0.25, 0.35, 0.85, 40)


def test_labeling_thresholds():
    assert (L.AUTO, L.MARGIN, L.TOPK, L.DUP_BITS) == (0.45, 0.10, 5, 12)


def test_expression_thresholds():
    js = (HERE / "expression.js").read_text("utf-8")
    m = re.search(r"const X_SURE = ([\d.]+), X_MARGIN = ([\d.]+), X_MIN_VOTES = (\d+);", js)
    assert m and m.groups() == ("0.45", "0.12", "3")


def test_tracker_strictness_default():
    html = (HERE / "tracker_ui.html").read_text("utf-8")
    assert re.search(r'id="optThresh"[^>]*value="0\.35"', html)
