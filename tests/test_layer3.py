"""Layer 3: the Kalman filter (explainable credits, dropouts, check-ins) and the honest comparison with layer 2."""
import math

import pytest

from fusion.evaluate import prospective
from fusion.kalman import DimensionFilter, SensorModel, fit_sensor_models


def _filter():
    return DimensionFilter(usual=4.0, spread=1.0, sensors={"hr": SensorModel(0.8, 0.3), "voice": SensorModel(0.4, 0.5)})


def test_credits_add_up_to_the_departure_from_usual():
    f = _filter()
    for k in range(50):
        f.reading(k * 30, "hr", 1.5)
        f.reading(k * 30 + 5, "voice", 0.5, quality=0.5)
    f.checkin(1600, 6)
    e = f.estimate(2000)
    assert math.isclose(e["value"] - e["usual"], sum(e["contributions"].values()), abs_tol=1e-9)
    assert set(e["contributions"]) == {"hr", "voice", "check-in"}


def test_silence_widens_the_band_and_relaxes_to_usual():
    f = _filter()
    for k in range(50):
        f.reading(k * 30, "hr", 2.0)
    busy = f.estimate(1500)
    later = f.estimate(1500 + 6 * 3600)
    assert busy["value"] > 5 and later["sd"] > busy["sd"]
    assert abs(later["value"] - 4.0) < abs(busy["value"] - 4.0) * 0.01


def test_untrusted_or_unknown_readings_change_nothing():
    f = _filter()
    f.reading(0, "hr", 3.0, quality=0.0)
    f.reading(1, "smile", 3.0)
    assert f.estimate(1)["value"] == pytest.approx(4.0) and f.estimate(1)["contributions"] == {}


def test_a_check_in_pulls_hard():
    f = _filter()
    f.checkin(0, 7)
    assert f.estimate(0)["value"] > 6


def test_sensor_models_from_data():
    levels = [(-1) ** k * (k % 5) / 2 for k in range(100)]
    got = fit_sensor_models(levels, {"hr": [0.8 * x for x in levels], "few": [1.0] * 5 + [None] * 95})
    assert got["hr"].loading == pytest.approx(0.8) and "few" not in got


def test_kalman_is_measured_against_layer_2(fortnight):
    """The rule: layer 3 is used only if it beats layer 2 on held-out data. On the simulated fortnight it doesn't
    (as of 2026-11-10: error 0.76 vs 0.62); this test keeps that comparison running, whichever way it comes out."""
    f, _, day7 = fortnight
    live = prospective(f, "energized", after=day7)
    assert live["kalman"]["n"] == live["linear"]["n"] > 50
    assert live["kalman"]["corr"] > 0.6                           # it tracks the level ...
    assert live["kalman"]["mae"] is not None                      # ... and its error is on record for the choice
