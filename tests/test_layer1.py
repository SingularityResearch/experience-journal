"""Layer 1: personal normals, trust-weighted windows, the away score."""
import math
import random

from fusion.away import away_from_normal
from fusion.baselines import MIN_N, Baselines, RobustNormal, situation
from fusion.engine import MAX_PAUSE, Z_CLIP, Fusion
from fusion.simulate import START
from fusion.windows import EWMA, SignalWindows

MORNING = START + 9 * 3600


def test_normal_ignores_rare_spikes():
    rng = random.Random(1)
    nm = RobustNormal(every=0)
    for k in range(1000):
        nm.add(70 + rng.gauss(0, 3) + (300 if k % 100 == 0 else 0), k)
    med, spread = nm.stats()
    assert abs(med - 70) < 0.6 and abs(spread - 3) < 0.6        # ten readings of 370 changed nothing


def test_normal_keeps_one_reading_per_interval():
    nm = RobustNormal(every=30)
    for t in range(0, 300):
        nm.add(1.0, t)
    assert nm.n == 10


def test_situation_normal_used_once_it_has_enough_readings():
    b = Baselines(every=0, min_n=MIN_N)
    for k in range(MIN_N):
        b.learn("A", "hr", 60.0 + (k % 3), MORNING + k, company=False)
    assert b.normal("A", "hr", MORNING, company=False)[2] == "situation"
    evening_with_others = START + 20 * 3600
    assert situation(evening_with_others, True) == "evening-company"
    assert b.normal("A", "hr", evening_with_others, company=True)[2] == "overall"   # that situation is still new
    assert b.z("B", "hr", 60.0, MORNING) is None                                     # nobody else's normal is used


def test_unusual_stretches_are_not_learned():
    b = Baselines(every=0, min_n=10)
    for k in range(20):
        b.learn("A", "hr", 60.0, MORNING + k)
    for k in range(20, 200):
        b.learn("A", "hr", 120.0, MORNING + k, unusual=True)
    assert b.normal("A", "hr", MORNING)[0] == 60.0


def test_ewma_handles_uneven_gaps_and_staleness():
    a, b = EWMA(60), EWMA(60)
    a.add(0, 1.0)
    a.add(60, 3.0)
    for t in (0, 20, 40):                     # the same first reading, then the same second one, with steps between
        b.add(t, 1.0, quality=1.0 if t == 0 else 0.0)
    b.add(60, 3.0)
    assert math.isclose(a.value(60)[0], b.value(60)[0])
    _, fresh = a.value(60)
    _, stale = a.value(60 + 600)
    assert stale < fresh * 0.001               # a silent sensor stops counting


def test_quality_weights_the_average():
    e = EWMA(1e9)                              # no forgetting: a plain weighted mean
    e.add(0, 0.0, quality=1.0)
    e.add(1, 10.0, quality=0.25)
    assert math.isclose(e.value(1)[0], 2.0)


def test_windows_can_be_read_back_with_a_delay():
    w = SignalWindows()
    for t in range(0, 1200, 10):
        w.add(t, 1.0 if t < 600 else -1.0)
    now = w.value(1190)["30s"][0]
    before = w.value(1190, lag=900)["30s"][0]
    assert now < -0.9 and before > 0.9
    assert w.value(1190, lag=7200) is None     # older than the kept history


def test_away_contributions_add_up_exactly():
    r = away_from_normal({"hr": (2.0, 1.0), "voice": (-1.0, 0.5), "smile": (0.0, 1.0), "off": (5.0, 0.0)})
    assert math.isclose(sum(r["contributions"].values()), r["score"] ** 2)
    assert math.isclose(sum(r["shares"].values()), 1.0)
    assert "off" not in r["contributions"] and r["signals"] == 3
    assert away_from_normal({})["score"] is None


def test_a_signal_that_is_usually_zero_still_gets_a_usable_spread():
    rng = random.Random(2)
    nm = RobustNormal(every=0)
    for k in range(400):
        nm.add(0.0 if rng.random() < 0.9 else 1.0, k)
    med, spread = nm.stats()
    assert med == 0.0 and 0.05 < spread < 0.3                       # mean absolute deviation, not 1e-6
    assert RobustNormal(every=0, resolution=0.5).stats() is None
    flat = RobustNormal(every=0, resolution=0.5)
    for k in range(10):
        flat.add(3.0, k)
    assert flat.stats()[1] == 0.5                                   # never finer than the sensor's own step


def _steady(f, t, steps, hr=70.0, rng=None):
    rng = rng or random.Random(0)
    for _ in range(steps):
        f.add("A", "hr", t, hr + rng.gauss(0, 3))
        f.add("A", "smile", t, 0.3 + rng.gauss(0, 0.1))
        t += 30
    return t


def test_one_moved_sensor_pauses_only_its_own_normal_and_not_for_ever():
    f = Fusion()
    rng = random.Random(1)
    t = _steady(f, MORNING, 360, rng=rng)                           # 3 hours at the usual 70
    smile_before = f.baselines.normals[("A", "smile", None)].n
    t = _steady(f, t, 120, hr=90.0, rng=rng)                        # 1 hour: heart rate sensor moved (+20)
    assert f.last[("A", "hr")]["learning"] == "paused"
    assert f.baselines.normal("A", "hr", t)[0] < 72                 # not learned during the pause ...
    assert f.baselines.normals[("A", "smile", None)].n > smile_before + 100   # ... but smile kept learning
    t = _steady(f, t, int((MAX_PAUSE + 4 * 3600) / 30), hr=90.0, rng=rng)
    assert f.baselines.normals[("A", "hr", None)].stats()[0] > 85   # after MAX_PAUSE the normal follows
    statuses = {r["learning"] for r in f.recent[("A", "hr")]}
    assert statuses <= {"relearning", "learning"}


def test_z_scores_are_clipped_before_smoothing():
    f = Fusion()
    t = _steady(f, MORNING, 200)
    z = f.add("A", "hr", t, 70 + 300)                               # a wild glitch
    assert z > 50                                                   # shown as it was ...
    m, _ = f.signals[("A", "hr")].value(t)["30s"]
    assert m <= Z_CLIP                                              # ... but counted as at most Z_CLIP


def test_a_late_reading_counts_as_if_it_had_arrived_on_time():
    on_time, late = EWMA(60), EWMA(60)
    on_time.add(0, 1.0)
    on_time.add(30, 2.0)
    on_time.add(60, 3.0)
    late.add(0, 1.0)
    late.add(60, 3.0)
    late.add(30, 2.0)                                               # arrives after the newer one
    assert math.isclose(on_time.value(60)[0], late.value(60)[0])
    assert math.isclose(on_time.value(60)[1], late.value(60)[1])


def test_a_check_ins_features_use_readings_up_to_it_only():
    def run(spike_after):
        f = Fusion()
        t = _steady(f, MORNING, 300)
        f.checkin("A", t - 15, {"energized": 5})
        if spike_after:
            for k in range(4):
                f.add("A", "hr", t + k * 30, 140.0)                 # readings after the check-in
        _steady(f, t + 120, 20)
        assert not f.pending
        return f.checkins[-1]["features"][0.0]["hr:30s"]
    assert run(False) == run(True)
