"""Layer 2: the group Bayesian linear model, on exact synthetic data and on the simulated fortnight."""
import math

import numpy as np
import pytest

from fusion.evaluate import forward_chain, metrics, prospective
from fusion.linear import GroupLinear

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
    m = GroupLinear(FEATS).fit(_people())
    for p, (usual, w) in {"A": (4.0, [0.8, 0.3, 0.0]), "B": (4.5, [0.6, 0.5, 0.0])}.items():
        got_usual, got = m.weights(p)
        assert abs(got_usual - usual) < 0.15
        assert all(abs(got[f] - want) < 0.12 for f, want in zip(FEATS, w))


def test_contributions_add_up_and_missing_features_are_listed():
    m = GroupLinear(FEATS).fit(_people())
    r = m.predict("A", {"hr": 1.5, "voice": -0.5, "noise": None})
    assert math.isclose(r["usual"] + sum(r["contributions"].values()), r["value"])
    assert r["missing"] == ["noise"] and r["contributions"]["noise"] == 0.0 and r["fitted_to"] == "own"


def test_a_new_person_starts_from_the_group_with_a_wider_band():
    m = GroupLinear(FEATS).fit(_people())
    known = m.predict("A", {"hr": 1.0, "voice": 0.0, "noise": 0.0})
    new = m.predict("C", {"hr": 1.0, "voice": 0.0, "noise": 0.0})
    assert new["fitted_to"] == "group" and new["sd"] > known["sd"]
    assert 0.5 < m.weights("C")[1]["hr"] < 0.9                  # between A's and B's


def test_pooling_helps_someone_with_few_check_ins():
    """C has 8 check-ins; the group has hundreds. Pooled weights should be closer to C's true ones than C alone."""
    true_c = [0.7, 0.4, 0.0]
    weights = {"A": (4.0, [0.8, 0.3, 0.0]), "B": (4.5, [0.6, 0.5, 0.0]), "C": (4.2, true_c)}
    errs = {True: [], False: []}
    for seed in range(20):
        data = _people(seed, n={"A": 200, "B": 200, "C": 8}, weights=weights)
        for pool in (True, False):
            _, w = GroupLinear(FEATS, pool=pool).fit(data).weights("C")
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
        imp, sd = model.importance(p), model.uncertainty(p)
        relevant = sum(imp[f] for f in imp if f.split(":")[0] in ("heart_rate", "posture"))
        smile = imp["smile:30s"] + imp["smile:10min"]
        assert relevant > 3 * smile
        assert all(imp[f] < 2.5 * sd[f] for f in ("smile:30s", "smile:10min"))   # smile has nothing to do with it
        assert imp["heart_rate:30s"] > 2 * sd["heart_rate:30s"]                    # heart rate clearly does


def test_beats_the_simple_baselines_with_an_honest_band(fortnight):
    f, _, _ = fortnight
    r = forward_chain(f, "energized")
    assert r["fusion"]["mae"] < 0.75 * r["your average"]["mae"]
    assert r["fusion"]["mae"] < r["your last check-in"]["mae"]
    assert 0.6 <= r["fusion"]["coverage70"] <= 0.85
    assert "energized" in f.models                                  # forward_chain left the engine's model alone


def test_beats_the_simple_baselines_on_other_seeds(other_fortnight):
    r = forward_chain(other_fortnight, "energized")
    assert r["fusion"]["mae"] < 0.8 * r["your average"]["mae"]
    assert 0.6 <= r["fusion"]["coverage70"] <= 0.9
    assert "energized" not in other_fortnight.models               # nothing was attached before, nothing is now


def test_missing_features_widen_the_band_never_narrow_it():
    m = GroupLinear(FEATS).fit(_people())
    full = m.predict("A", {"hr": 1.5, "voice": 0.0, "noise": 0.0})
    no_hr = m.predict("A", {"hr": None, "voice": 0.0, "noise": 0.0})
    no_noise = m.predict("A", {"hr": 1.5, "voice": 0.0, "noise": None})
    assert no_hr["sd"] > 1.5 * full["sd"]                           # hr matters: not knowing it is a real loss
    assert no_hr["sd"] == pytest.approx(math.sqrt(0.25 + 0.8 ** 2), rel=0.15)
    assert full["sd"] <= no_noise["sd"] < full["sd"] * 1.05         # an irrelevant feature costs almost nothing


def test_missing_features_correlated_with_present_ones_cost_less():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(300, 3))
    X[:, 1] = X[:, 0] + rng.normal(0, 0.3, 300)                     # voice nearly a copy of hr
    y = 4 + X @ np.array([0.5, 0.5, 0.0]) + rng.normal(0, 0.5, 300)
    m = GroupLinear(FEATS).fit({"A": (X, y)})
    alone = GroupLinear(FEATS).fit({"A": (np.c_[X[:, 0], rng.normal(size=(300, 2))], y)})
    assert m.predict("A", {"hr": 1.0, "voice": None, "noise": 0.0})["sd"] < \
        alone.predict("A", {"hr": 1.0, "voice": None, "noise": 0.0})["sd"] + 0.3


def test_noise_and_pooling_strength_are_chosen_from_the_data():
    m = GroupLinear(FEATS).fit(_people())
    assert m.sigma2 == pytest.approx(0.25, rel=0.25)                # the made-up people's noise: 0.5 squared
    same = {"A": (4.0, [0.7, 0.4, 0.0]), "B": (4.0, [0.7, 0.4, 0.0])}
    apart = {"A": (4.0, [1.2, -0.2, 0.0]), "B": (4.0, [0.0, 1.0, 0.0])}
    assert GroupLinear(FEATS).fit(_people(weights=same)).tau2 < GroupLinear(FEATS).fit(_people(weights=apart)).tau2


def test_a_new_persons_band_includes_the_group_averages_uncertainty():
    m = GroupLinear(FEATS).fit(_people(n={"A": 30, "B": 30}))
    assert np.all(np.diag(m.group_cov) > 0)
    new = m.predict("C", {"hr": 1.0, "voice": 0.0, "noise": 0.0})
    x = np.r_[1.0, 1.0 / m.scale[0], 0.0, 0.0]
    without = math.sqrt(m.sigma2 + x @ np.diag(m._prior(m.tau2)) @ x)
    assert new["sd"] > without


def test_live_predictions_were_made_before_each_check_in(fortnight):
    f, _, day7 = fortnight
    live = prospective(f, "energized", after=day7)
    assert live["linear"]["n"] > 50 and live["linear"]["corr"] > 0.6


def test_why_view_explains_the_estimate(fortnight):
    f, _, _ = fortnight
    f.fit("energized")
    t = f.last[("A", "heart_rate")]["t"]
    ex = f.explain("A", t, "energized")
    rows = {r["signal"]: r for r in ex["rows"]}
    assert set(rows) == {"heart_rate", "speech_rate", "posture", "smile"}
    est = ex["estimate"]
    total = est["usual"] + sum(r.get("contribution", 0.0) for r in ex["rows"])
    assert est["value"] == pytest.approx(total)
    assert all(r["normal"] is not None and r["spread"] > 0 for r in rows.values())
    # every contribution can be checked by hand: weight x the window value shown beside it
    for r in rows.values():
        for feat in r["features"].values():
            assert feat["contribution"] == pytest.approx(feat["weight"] * (feat["value"] or 0.0))
        assert r["contribution"] == pytest.approx(sum(feat["contribution"] for feat in r["features"].values()))


def test_why_view_of_a_past_moment_uses_only_what_was_known_then(fortnight):
    f, _, _ = fortnight
    f.fit("energized")
    now = f.last[("A", "heart_rate")]["t"]
    then = now - 1200
    past = f.explain("A", then, "energized")
    assert all(r["t"] is None or r["t"] <= then for r in past["rows"])
    assert past["estimate"]["value"] != pytest.approx(f.explain("A", now, "energized")["estimate"]["value"])
