"""
Made-up people for testing the fusion (no real data): each has a hidden "energized" level that drifts through the
day, sensors that follow it in their own way (some with a delay, some noisy, some only part of the time, one
that has nothing to do with it), occasional glitches, and check-ins a few times a day.

Because the truth is known, tests can check that the fusion finds the right signals, the right delays and honest
uncertainty. Nothing here is a claim about real people.
"""
import math
import random
import time

START = time.mktime((2026, 1, 5, 0, 0, 0, 0, 0, -1))     # a Monday, local midnight
WAKE, SLEEP = 7, 23                                      # hours awake (sensors only send while awake)

# How each person's sensors follow their level s (1-7 scale, usual 4): value = base + gain x (s - 4) + noise.
# Person "B" reacts more in heart rate and less in voice: the family model has to learn each one's own weights.
PEOPLE = {
    "A": {"heart_rate": (70, 5.0, 3.0), "speech_rate": (3.8, 0.35, 0.25), "posture": (2.0, 1.2, 2.0),
          "smile": (0.25, 0.0, 0.10)},
    "B": {"heart_rate": (66, 8.0, 3.0), "speech_rate": (4.2, 0.15, 0.25), "posture": (1.0, 1.0, 2.0),
          "smile": (0.30, 0.0, 0.10)},
}
DELAY = {"heart_rate": 120.0}          # seconds the signal lags the level
TALKING_SHARE = 0.4                    # speech rate only while talking (other times: no reading)
GLITCH = 1 / 3000                      # chance of a wild reading


def simulate(engine, days=14, step=30.0, checkins_per_day=5, seed=0, people=PEOPLE, on_day=None):
    """Feed `days` of made-up readings and check-ins into the engine. Returns {person: [(t, level)]} (the truth,
    sampled every 10 minutes). on_day(engine, day_index, day_start) is called at each local midnight."""
    rng = random.Random(seed)
    truth = {p: [] for p in people}
    levels = {p: 4.0 for p in people}
    tau, spread = 2 * 3600.0, 1.2                  # level drifts with this time constant and spread
    history = {p: [] for p in people}              # (t, level) for delayed signals
    for d in range(days):
        day0 = START + d * 86400
        if on_day:
            on_day(engine, d, day0)
        times = sorted(day0 + rng.uniform(WAKE * 3600 + 900, SLEEP * 3600 - 900) for _ in range(checkins_per_day))
        t = day0 + WAKE * 3600
        end = day0 + SLEEP * 3600
        talking = {p: False for p in people}
        while t < end:
            phi = math.exp(-step / tau)
            for p, sensors in people.items():
                levels[p] = 4 + phi * (levels[p] - 4) + rng.gauss(0, spread * math.sqrt(1 - phi * phi))
                history[p].append((t, levels[p]))
                if len(history[p]) > 40:
                    history[p].pop(0)
                if rng.random() < 0.02:
                    talking[p] = rng.random() < TALKING_SHARE
                for s, (base, gain, noise) in sensors.items():
                    if s == "speech_rate" and not talking[p]:
                        continue
                    lvl = _level_at(history[p], t - DELAY.get(s, 0.0))
                    v = base + gain * (lvl - 4) + rng.gauss(0, noise)
                    if rng.random() < GLITCH:
                        v += rng.choice((-1, 1)) * 10 * noise
                    quality = rng.uniform(0.3, 1.0) if s == "posture" else 1.0
                    engine.add(p, s, t, v, quality=quality)
                if int(t - day0) % 600 == 0:
                    truth[p].append((t, levels[p]))
            while times and times[0] <= t:
                ct = times.pop(0)
                for p in people:
                    rating = min(7, max(1, round(levels[p] + rng.gauss(0, 0.5))))
                    engine.checkin(p, ct, {"energized": rating})
            t += step
    return truth


def _level_at(history, t):
    for ht, lv in reversed(history):
        if ht <= t:
            return lv
    return history[0][1]
