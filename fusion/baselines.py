"""
Each person's normal for each signal: layer 1 of the fusion (docs/DESIGN.md §6).

A normal is the median and the typical spread (MAD, scaled to match a standard deviation for normal data) of that
person's recent readings, so a rare spike doesn't warp it. It is kept per situation (part of day, alone or in
company) and overall; the situation's normal is used once it has enough readings, the overall one until then.
It adapts slowly: one reading is kept per SAMPLE_EVERY seconds, the last KEEP of them (about 2 days of waking time
at the defaults). The caller pauses learning during unusual stretches (`learn(..., unusual=True)` does nothing),
so a bad stretch doesn't become the new normal (the engine pauses each signal separately, and for a limited time).

The spread never collapses to zero: a signal that is usually exactly 0 (a laugh, a blink count) has a MAD of 0, so
the mean absolute deviation (scaled to match a standard deviation) is used instead, and never less than the
signal's resolution (the smallest step the sensor reports), when the sensor states one.
"""
import time
from collections import deque

import numpy as np

SAMPLE_EVERY = 30.0      # seconds between readings kept for the normal (readings in between still get z-scores)
KEEP = 5000              # readings kept per normal
MIN_N = 120              # readings a normal needs before it is used (about an hour at SAMPLE_EVERY)
MAD_TO_SD = 1.4826       # MAD x this = standard deviation, for normally distributed data
MEANAD_TO_SD = 1.2533    # mean absolute deviation x this = standard deviation, for normally distributed data
MIN_SPREAD = 1e-6        # a signal that never varies still gets a usable (tiny) spread
PARTS_OF_DAY = ((0, "night"), (6, "morning"), (12, "afternoon"), (18, "evening"))


def part_of_day(t):
    """'night' | 'morning' | 'afternoon' | 'evening' for a Unix time, in this computer's time zone."""
    hour = time.localtime(t).tm_hour
    return [name for start, name in PARTS_OF_DAY if hour >= start][-1]


def situation(t, company):
    return f"{part_of_day(t)}-{'company' if company else 'alone'}"


class RobustNormal:
    """Median and spread of the readings kept for one person, signal and situation."""

    def __init__(self, keep=KEEP, every=SAMPLE_EVERY, resolution=0.0):
        self.values = deque(maxlen=keep)
        self.every = every
        self.resolution = float(resolution or 0.0)
        self.last_t = None
        self._stats = None
        self._new = 0            # readings kept since the median was last worked out

    @property
    def n(self):
        return len(self.values)

    def add(self, value, t):
        if self.last_t is not None and t - self.last_t < self.every:
            return
        self.values.append(float(value))
        self.last_t = t
        self._new += 1
        # the median moves slowly: work it out again after 2% new readings (always while the normal is young)
        if self._stats is not None and (self._new >= max(1, len(self.values) // 50) or len(self.values) < 2 * MIN_N):
            self._stats = None

    def stats(self):
        """(median, spread) of the kept readings, or None when there are none."""
        if self._stats is None and self.values:
            v = np.fromiter(self.values, float)
            med = float(np.median(v))
            dev = np.abs(v - med)
            spread = float(np.median(dev)) * MAD_TO_SD
            if spread <= 0:              # more than half the readings are the same value (usually 0)
                spread = float(dev.mean()) * MEANAD_TO_SD
            self._stats = (med, max(spread, self.resolution, MIN_SPREAD, abs(med) * 1e-4))
            self._new = 0
        return self._stats


class Baselines:
    """All normals: (person, signal, situation) and (person, signal, overall)."""

    def __init__(self, keep=KEEP, every=SAMPLE_EVERY, min_n=MIN_N, resolution=None):
        self.keep, self.every, self.min_n = keep, every, min_n
        self.resolution = dict(resolution or {})     # signal -> smallest step its sensor reports (optional)
        self.normals = {}

    def _normal(self, key):
        if key not in self.normals:
            self.normals[key] = RobustNormal(self.keep, self.every, self.resolution.get(key[1], 0.0))
        return self.normals[key]

    def learn(self, person, signal, value, t, company=False, unusual=False):
        if unusual or value is None or not np.isfinite(value):
            return
        self._normal((person, signal, situation(t, company))).add(value, t)
        self._normal((person, signal, None)).add(value, t)

    def normal(self, person, signal, t, company=False):
        """(median, spread, which) for the reading's situation, or the overall normal while that one is too new;
        None while neither has MIN_N readings."""
        for key, which in (((person, signal, situation(t, company)), "situation"), ((person, signal, None), "overall")):
            nm = self.normals.get(key)
            if nm and nm.n >= self.min_n:
                med, spread = nm.stats()
                return med, spread, which
        return None

    def z(self, person, signal, value, t, company=False):
        """How many spreads value is from this person's normal (None while there's no normal yet). Not clipped:
        the engine clips it (Z_CLIP) before smoothing, and shows both."""
        nm = self.normal(person, signal, t, company)
        if nm is None:
            return None
        med, spread, _ = nm
        return (value - med) / spread
