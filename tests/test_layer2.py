"""Layer 2: the family Bayesian linear model, on exact synthetic data and on the simulated fortnight."""
import math

import numpy as np
import pytest

from fusion.evaluate import forward_chain, metrics, prospective
from fusion.linear import FamilyLinear

FEATS = ["hr", "voice", "noise"]


def _people(seed=0, n=None, weights=None):
    rng = np.random.default_rng(seed)
    n = n or {"A": 200, "B": 200}
    weights = weights or {"A": (4.0, [0.8, 0.3, 0.0]), "B": (4.5, [0.6, 0.5, 0.0])}
    data = {}
    for p, (usual, w) in weights.items():
        X = rng.normal(size=(n[p], 3))
        y = usual + X @ np.array(w) + rng.normal(0, 0.5, n[p])
        data[p] = (X, y)
    return data


def test_recovers_each_persons_weights_with_plenty_of_data():
    m = FamilyLinear(FEATS).fit(_people())
    for p, (usual, w) in {"A": (4.0, [0.8, 0.3, 0.0]), "B": (4.5, [0.6, 0.5, 0.0])}.items():
        got_usual, got = m.weights(p)
        assert abs(got_usual - usual) < 0.15
        assert all(abs(got[f] - want) < 0.12 for f, want in zip(FEATS, w))


def test_contributions_add_up_and_missing_features_are_listed():
    m = FamilyLinear(FEATS).fit(_people())
    r = m.predict("A", {"hr": 1.5, "voice": -0.5, "noise": None})
    assert math.isclose(r["usual"] + sum(r["contributions"].values()), r["value"])
    assert r["missing"] == ["noise"] and r["contributions"]["noise"] == 0.0 and r["fitted_to"] == "own"


def test_a_new_person_starts_from_the_family_with_a_wider_band():
    m = FamilyLinear(FEATS).fit(_people())
    known = m.predict("A", {"hr": 1.0, "voice": 0.0, "noise": 0.0})
    new = m.predict("C", {"hr": 1.0, "voice": 0.0, "noise": 0.0})
    assert new["fitted_to"] == "family" and new["sd"] > known["sd"]
    assert 0.5 < m.weights("C")[1]["hr"] < 0.9                  # between A's and B's


def test_pooling_helps_someone_with_few_check_ins():
    """C has 8 check-ins; the family has hundreds. Pooled weights should be closer to C's true ones than C alone."""
    true_c = [0.7, 0.4, 0.0]
    weights = {"A": (4.0, [0.8, 0.3, 0.0]), "B": (4.5, [0.6, 0.5, 0.0]), "C": (4.2, true_c)}
    errs = {True: [], False: []}
    for seed in range(20):
        data = _people(seed, n={"A": 200, "B": 200, "C": 8}, weights=weights)
        for pool in (True, False):
            _, w = FamilyLinear(FEATS, pool=pool).fit(data).weights("C")
            errs[pool].append(sum((w[f] - t) ** 2 for f, t in zip(FEATS, true_c)))
    assert np.mean(errs[True]) < 0.5 * np.mean(errs[False])


def test_metrics():
    m = metrics([(4, 4.0, 1.0), (5, 4.0, 1.0), (6, 4.0, 1.0)])
    assert m["n"] == 3 and math.isclose(m["mae"], 1.0) and math.isclose(m["coverage70"], 2 / 3)


def test_finds_the_signals_that_matter_and_their_delays(fortnight):
    f, _, _ = fortnight
    model = f.fit("energized")
    lags = f.models["energized"][1]
    # built in: 120 s. With a slow mood and a few check-ins a day, 0-120 s look nearly the same (DESIGN.md §6),
    # so only "short, not the longest" can be asked of check-ins; reactions to known moments will pin it down.
    assert lags["heart_rate"] in (0.0, 60.0, 120.0)
    for p in ("A", "B"):
        imp = model.importance(p)
        hr = imp["heart_rate:30s"] + imp["heart_rate:10min"]
        smile = imp["smile:30s"] + imp["smile:10min"]
        assert hr > 3 * smile                                       # smile has nothing to do with it


def test_beats_the_simple_baselines_with_an_honest_band(fortnight):
    f, _, _ = fortnight
    r = forward_chain(f, "energized")
    assert r["fusion"]["mae"] < 0.75 * r["your average"]["mae"]
    assert r["fusion"]["mae"] < r["your last check-in"]["mae"]
    assert 0.55 <= r["fusion"]["coverage70"] <= 0.85


def test_live_predictions_were_made_before_each_check_in(fortnight):
    f, _, day7 = fortnight
    live = prospective(f, "energized", after=day7)
    assert live["linear"]["n"] > 50 and live["linear"]["corr"] > 0.6


def test_why_view_explains_the_estimate(fortnight):
    f, _, _ = fortnight
    t = f.last[("A", "heart_rate")]["t"]
    ex = f.explain("A", t, "energized")
    rows = {r["signal"]: r for r in ex["rows"]}
    assert set(rows) == {"heart_rate", "speech_rate", "posture", "smile"}
    est = ex["estimate"]
    total = est["usual"] + sum(r.get("contribution", 0.0) for r in ex["rows"])
    assert est["value"] == pytest.approx(total)
    assert all(r["normal"] is not None and r["spread"] > 0 for r in rows.values())
