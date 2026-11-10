"""
Fusion over time: layer 3 of the fusion (docs/DESIGN.md §6). Kept only if it beats layer 2 on held-out weeks.

One person's one dimension (for example "energized") is a hidden level s that drifts and is pulled back toward their
usual level m with time constant TAU (an Ornstein-Uhlenbeck process: in a quiet hour it relaxes to normal). Each
sensor's smoothed z-score is a noisy view of it:  z_i = b_i + a_i (s - m) + noise_i,  with the noise larger when the
reading is less trustworthy (variance r_i / quality); b_i allows for the sensor's normal (a median) not sitting
exactly at the person's usual rating (a mean). A check-in is a direct, small-noise view: rating = s + noise.

A Kalman filter updates s and its uncertainty P at every reading, so sensors arriving at different rates combine
naturally, a silent sensor simply stops contributing, and the uncertainty widens while little is heard.
It stays explainable: every update moves s by gain x surprise, credited to the sensor that caused it, and these
credits decay with the same pull back to normal, so at any moment  s - m == sum of the credits  exactly.

The filter assumes each reading's noise is independent of the last one's. Smoothed windows read every few seconds
aren't, so the engine feeds each sensor at most every FILTER_EVERY seconds (engine.py); fed every 30 s on simulated
data, the band was far too narrow (54% held for a 70% band).
Still to try when real data exists: fitting TAU and the noise by the likelihood of each next reading on training
days, and allowing for the noise in the check-ins the loadings are fitted to (it shrinks them toward 0).
"""
import math

import numpy as np

TAU = 3600.0             # seconds for a departure from the usual level to fade by 1/e
CHECKIN_VAR = 0.33       # variance of a check-in around the true level (about +-0.5, plus rounding to whole numbers)


class SensorModel:
    """How one sensor's smoothed z relates to the dimension: z = offset + loading x (s - usual) + noise of variance
    noise_var."""

    def __init__(self, loading, noise_var, offset=0.0):
        self.loading, self.noise_var = float(loading), max(float(noise_var), 1e-6)
        self.offset = float(offset)


def fit_sensor_models(levels, readings, min_n=20):
    """Loadings from data: levels = the dimension's level minus usual at some times (check-ins, or a fitted
    estimate), readings = {sensor: z at the same times (None where missing)}. Least squares per sensor, with an
    offset."""
    out = {}
    lv = np.asarray(levels, float)
    for sensor, zs in readings.items():
        z = np.array([np.nan if v is None else v for v in zs], float)
        ok = np.isfinite(z) & np.isfinite(lv)
        if ok.sum() < min_n or np.var(lv[ok]) < 1e-9:
            continue
        a = float(np.cov(lv[ok], z[ok])[0, 1] / np.var(lv[ok], ddof=1))
        b = float(z[ok].mean() - a * lv[ok].mean())
        resid = z[ok] - b - a * lv[ok]
        out[sensor] = SensorModel(a, float(resid @ resid) / max(1, ok.sum() - 2), offset=b)
    return out


class DimensionFilter:
    """One person's one dimension over time."""

    def __init__(self, usual, spread, sensors, tau=TAU, checkin_var=CHECKIN_VAR):
        self.m = float(usual)
        self.stationary_var = max(float(spread) ** 2, 1e-6)   # how far a person's level typically ranges
        self.sensors = sensors                                # {sensor: SensorModel}
        self.tau = tau
        self.checkin_var = checkin_var
        self.s = self.m
        self.P = self.stationary_var
        self.t = None
        self.credits = {}

    def _advance(self, t):
        if self.t is not None and t > self.t:
            phi = math.exp(-(t - self.t) / self.tau)
            self.s = self.m + phi * (self.s - self.m)
            self.P = phi * phi * self.P + self.stationary_var * (1 - phi * phi)
            for k in self.credits:
                self.credits[k] *= phi
        self.t = t if self.t is None else max(self.t, t)

    def _update(self, source, observed, loading, noise_var):
        S = loading * loading * self.P + noise_var
        gain = self.P * loading / S
        move = gain * (observed - loading * (self.s - self.m))
        self.s += move
        self.P -= gain * loading * self.P
        self.credits[source] = self.credits.get(source, 0.0) + move

    def reading(self, t, sensor, z, quality=1.0):
        """A sensor's smoothed z-score at time t (ignored for unknown sensors or no trust)."""
        self._advance(t)
        model = self.sensors.get(sensor)
        if model is None or quality <= 0 or z is None or not math.isfinite(z):
            return
        self._update(sensor, z - model.offset, model.loading, model.noise_var / quality)

    def checkin(self, t, rating):
        """The person's own rating: the most direct view there is."""
        self._advance(t)
        # a check-in observes s itself (not s - m), so express it relative to m with loading 1
        self._update("check-in", rating - self.m, 1.0, self.checkin_var)

    def estimate(self, t):
        """{"value", "sd", "rating_sd", "usual", "contributions": {source: part of value - usual}} at time t.
        sd is the uncertainty of the level itself; rating_sd adds the noise of a check-in, so it is the spread to
        expect for the person's next rating (the one to compare with check-ins)."""
        self._advance(t)
        return {"value": self.s, "sd": math.sqrt(self.P), "rating_sd": math.sqrt(self.P + self.checkin_var),
                "usual": self.m, "contributions": dict(self.credits)}
