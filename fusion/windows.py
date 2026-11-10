"""
Smoothing over several time windows: layer 1 of the fusion (docs/DESIGN.md §6).

Each window is an exponentially weighted moving average of a signal's z-scores, weighted by each reading's trust
(quality 0-1) and correct for irregular gaps between readings. Besides its value, a window reports its support: the
decayed sum of the trust it has seen. Support falls while a sensor is silent (phone in a pocket, face off camera),
which tells later layers how much to rely on it. A short history of each window is kept, so the value a little
earlier (the body reacts seconds to minutes after what you saw), or at a moment that has passed, can be read back.

A reading that arrives late (older than the newest one, from a device that buffered while the hub was away) counts
with the weight it would have left by now, as if it had arrived on time; the saved history isn't rewritten.
"""
import math
from collections import deque

WINDOWS = {"30s": 30.0, "10min": 600.0, "1day": 86400.0}   # name -> time constant in seconds
HISTORY_EVERY = 10.0     # seconds between saved window values
HISTORY_KEEP = 3600.0    # seconds of window values kept (for lagged reads)


class EWMA:
    """Trust-weighted exponential moving average with time constant tau seconds."""

    def __init__(self, tau):
        self.tau = tau
        self.mean = 0.0
        self.support = 0.0
        self.t = None

    def _decay_to(self, t):
        if self.t is not None and t > self.t:
            self.support *= math.exp(-(t - self.t) / self.tau)
        self.t = t if self.t is None else max(self.t, t)

    def add(self, t, x, quality=1.0):
        if self.t is not None and t < self.t:      # late: it would have decayed this much by now
            quality *= math.exp(-(self.t - t) / self.tau)
        self._decay_to(t)
        if quality > 0:
            self.mean = (self.mean * self.support + quality * x) / (self.support + quality)
            self.support += quality

    def value(self, t):
        """(mean, support at time t)."""
        if self.t is None:
            return 0.0, 0.0
        dt = max(0.0, t - self.t)
        return self.mean, self.support * math.exp(-dt / self.tau)


class SignalWindows:
    """One signal's windows, with a short history of their values."""

    def __init__(self, windows=WINDOWS):
        self.windows = {name: EWMA(tau) for name, tau in windows.items()}
        self.history = deque()           # (t, {name: (mean, support)})
        self.last_saved = None

    def add(self, t, z, quality=1.0):
        for w in self.windows.values():
            w.add(t, z, quality)
        if self.last_saved is None or t - self.last_saved >= HISTORY_EVERY:
            self.history.append((t, {n: w.value(t) for n, w in self.windows.items()}))
            self.last_saved = t
            while self.history and t - self.history[0][0] > HISTORY_KEEP:
                self.history.popleft()

    @property
    def latest(self):
        """Time of the newest reading (None before any)."""
        return next(iter(self.windows.values())).t

    def value(self, t, lag=0.0):
        """{window: (mean, support)} at t - lag, from readings up to then only; None if the history doesn't reach
        back that far."""
        target = t - max(0.0, lag)
        if self.latest is None:
            return None
        if target >= self.latest:
            return {n: w.value(target) for n, w in self.windows.items()}
        best = None
        for ht, vals in reversed(self.history):
            if ht <= target:
                best = (ht, vals)
                break
        if best is None:
            return None
        ht, vals = best
        # support keeps decaying between the saved time and the target time
        return {n: (m, s * math.exp(-(target - ht) / self.windows[n].tau)) for n, (m, s) in vals.items()}
