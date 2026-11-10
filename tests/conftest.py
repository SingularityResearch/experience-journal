"""Shared setup: the repository on the import path, and one simulated fortnight shared by the slower tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fusion.engine import Fusion  # noqa: E402
from fusion.simulate import START, simulate  # noqa: E402


@pytest.fixture(scope="session")
def fortnight():
    """14 made-up days for people A and B: layer 2 refitted each midnight from day 5, Kalman filters from day 7,
    so the prediction log holds honest live predictions. Returns (engine, truth, START of day 7)."""
    def on_day(engine, d, day0):
        if d >= 5:
            engine.fit("energized", before=day0)
        if d == 7:
            engine.attach_filters("energized", before=day0)
    f = Fusion()
    truth = simulate(f, days=14, on_day=on_day)
    return f, truth, START + 7 * 86400


@pytest.fixture(scope="session", params=[1, 2])
def other_fortnight(request):
    """The same fortnight with other random seeds: a claim that holds on one seed only isn't a finding."""
    f = Fusion()
    simulate(f, days=14, seed=request.param)
    return f
