"""
The fusion engine: readings in, explained estimates out (docs/DESIGN.md §6).

    f = Fusion()
    f.add("ann", "heart_rate", t, 84, quality=0.9)       # every sensor reading, as it arrives
    f.checkin("ann", t, {"energized": 5})                 # the person's own ratings
    f.away("ann", t)                                      # "away from your normal", with each signal's share
    f.fit("energized")                                    # layer 2 from the check-ins so far (lags chosen too)
    f.explain("ann", t, "energized")                      # the "why" rows: raw, normal, z, weight, contribution

Layer 3 (the Kalman filter) is attached with attach_filter() once its sensor models are fitted. At every check-in,
the estimates the attached models made *before* seeing it are logged (prediction_log), which is how they are
measured honestly against each other (evaluate.py).
"""
import math

from fusion.away import away_from_normal
from fusion.baselines import Baselines
from fusion.kalman import DimensionFilter, fit_sensor_models
from fusion.linear import FamilyLinear
from fusion.windows import WINDOWS, SignalWindows

FEATURE_WINDOWS = ("30s", "10min")   # per signal, the model's inputs: a reaction window and a mood window
# (their difference, the "change", is shown in the why view but not fed to the model: it would be an exact copy of
#  the two, which makes the split of credit between them arbitrary)
LAGS = (0.0, 60.0, 120.0, 300.0)     # how far back each signal may be read (the body reacts after the moment)
FREEZE_AWAY = 3.0                    # a 10-minute "away" score above this pauses learning the person's normal
MIN_SUPPORT = 0.5                    # a window needs this much trust-weighted support to count
FILTER_EVERY = 30.0                  # seconds between a signal's readings fed to a Kalman filter


def weight_of(support):
    """Trust from a window's support: about 1 with plenty of recent readings, falling toward 0 when stale."""
    return support / (support + 1.0)


class Fusion:
    def __init__(self, windows=WINDOWS, baselines=None, lags=LAGS):
        self.window_spec = windows
        self.baselines = baselines or Baselines()
        self.lags = tuple(lags)
        self.signals = {}            # (person, signal) -> SignalWindows
        self.last = {}               # (person, signal) -> last reading {t, raw, z, quality, normal}
        self.checkins = []           # {person, t, ratings, features: {lag: {feature: value}}}
        self.models = {}             # dimension -> (FamilyLinear, {signal: lag})
        self.filters = {}            # (person, dimension) -> DimensionFilter
        self._fed = {}               # (person, dimension, signal) -> last time fed to the filter
        self.prediction_log = []     # {person, t, dimension, rating, predictions: {model: (value, sd)}}

    # ------------------------------------------------------------------ readings
    def add(self, person, signal, t, value, quality=1.0, company=False):
        """One sensor reading. Returns its z-score against the person's normal (None while that's being learned)."""
        z = self.baselines.z(person, signal, value, t, company)
        unusual = self.unusual(person, t)
        self.baselines.learn(person, signal, value, t, company, unusual=unusual)
        key = (person, signal)
        if z is not None:
            if key not in self.signals:
                self.signals[key] = SignalWindows(self.window_spec)
            self.signals[key].add(t, z, quality)
            self._feed_filters(person, signal, t)
        self.last[key] = {"t": t, "raw": value, "z": z, "quality": quality,
                          "normal": self.baselines.normal(person, signal, t, company)}
        return z

    def people(self):
        return sorted({p for p, _ in self.signals} | {c["person"] for c in self.checkins})

    def signal_names(self, person=None):
        return sorted({s for p, s in self.signals if person is None or p == person})

    def readings(self, person, t, window="10min", lag=0.0):
        """{signal: (z, weight)} from one window, for the away score."""
        out = {}
        for (p, s), w in self.signals.items():
            if p != person:
                continue
            vals = w.value(t, lag)
            if vals is not None:
                m, support = vals[window]
                out[s] = (m, weight_of(support))
        return out

    def away(self, person, t, window="10min"):
        """'Away from your normal' with each signal's exact share (see away.py)."""
        return away_from_normal(self.readings(person, t, window))

    def unusual(self, person, t):
        score = self.away(person, t)["score"]
        return score is not None and score > FREEZE_AWAY

    # ------------------------------------------------------------------ features (layer 2's inputs)
    def features(self, person, t, lags=None):
        """{feature: value or None}: for each signal, its 30-second and 10-minute windows and their difference,
        read lags[signal] seconds back (0 by default). None where there's too little recent data."""
        lags = lags or {}
        out = {}
        for s in self.signal_names():
            w = self.signals.get((person, s))
            vals = w.value(t, lags.get(s, 0.0)) if w else None
            for name in FEATURE_WINDOWS:
                m, sup = vals[name] if vals else (None, 0.0)
                out[f"{s}:{name}"] = m if sup >= MIN_SUPPORT else None
        return out

    def feature_names(self):
        return [f"{s}:{n}" for s in self.signal_names() for n in FEATURE_WINDOWS]

    # ------------------------------------------------------------------ check-ins
    def checkin(self, person, t, ratings):
        """The person's own ratings ({dimension: 1-7}). Logs what each attached model predicted just before."""
        for dim, rating in ratings.items():
            preds = {}
            if dim in self.models:
                model, lags = self.models[dim]
                r = model.predict(person, self.features(person, t, lags))
                preds["linear"] = (r["value"], r["sd"])
            filt = self.filters.get((person, dim))
            if filt is not None:
                e = filt.estimate(t)
                preds["kalman"] = (e["value"], e["rating_sd"])
                filt.checkin(t, rating)
            self.prediction_log.append({"person": person, "t": t, "dimension": dim, "rating": rating,
                                        "predictions": preds})
        self.checkins.append({"person": person, "t": t, "ratings": dict(ratings),
                              "features": {lag: self.features(person, t, {s: lag for s in self.signal_names()})
                                           for lag in self.lags}})

    def training_rows(self, dimension, lags=None, before=None, after=None):
        """{person: (rows of {feature: value}, ratings)} from stored check-ins, each signal read at its lag."""
        lags = lags or {}
        data = {}
        for c in self.checkins:
            if dimension not in c["ratings"] or (before is not None and c["t"] >= before) or \
                    (after is not None and c["t"] < after):
                continue
            row = {}
            for s in self.signal_names():
                feats = c["features"].get(lags.get(s, 0.0), {})
                for n in FEATURE_WINDOWS:
                    row[f"{s}:{n}"] = feats.get(f"{s}:{n}")
            rows, ys = data.setdefault(c["person"], ([], []))
            rows.append(row)
            ys.append(c["ratings"][dimension])
        return data

    def choose_lags(self, dimension, before=None):
        """For each signal, the lag whose 30-second window goes best with the ratings (largest |correlation|),
        judged on check-ins before `before` only. (The 10-minute window smooths a delay of a minute or two away.)"""
        best = {}
        for s in self.signal_names():
            scores = []
            for lag in self.lags:
                xs, ys = [], []
                for c in self.checkins:
                    if dimension in c["ratings"] and (before is None or c["t"] < before):
                        v = c["features"].get(lag, {}).get(f"{s}:30s")
                        if v is not None:
                            xs.append(v)
                            ys.append(c["ratings"][dimension])
                scores.append((abs(_corr(xs, ys)), lag))
            best[s] = max(scores)[1] if scores else 0.0
        return best

    def fit(self, dimension, before=None, pool=True):
        """Fit layer 2 for one dimension from the check-ins so far (or before a time). Returns the model."""
        lags = self.choose_lags(dimension, before)
        names = self.feature_names()
        data = {}
        for p, (rows, ys) in self.training_rows(dimension, lags, before).items():
            X = [[0.0 if r.get(f) is None else r[f] for f in names] for r in rows]
            data[p] = (X, ys)
        model = FamilyLinear(names, pool=pool).fit(data)
        self.models[dimension] = (model, lags)
        return model

    # ------------------------------------------------------------------ layer 3
    def attach_filter(self, person, dimension, usual, spread, levels, readings):
        """Start a Kalman filter for one person's dimension; sensor models fitted from (levels, readings) pairs
        (see kalman.fit_sensor_models)."""
        sensors = fit_sensor_models(levels, readings)
        self.filters[(person, dimension)] = DimensionFilter(usual, spread, sensors)
        return sensors

    def attach_filters(self, dimension, before=None):
        """Start a Kalman filter for everyone with check-ins on this dimension: their usual level and spread from
        their ratings, each sensor's loading from its 30-second window at those check-ins (before a time,
        optionally). Returns {person: {sensor: SensorModel}}."""
        out = {}
        for p in self.people():
            cis = [c for c in self.checkins if c["person"] == p and dimension in c["ratings"]
                   and (before is None or c["t"] < before)]
            if len(cis) < 10:
                continue
            ys = [c["ratings"][dimension] for c in cis]
            usual = sum(ys) / len(ys)
            spread = (sum((y - usual) ** 2 for y in ys) / (len(ys) - 1)) ** 0.5
            readings = {s: [c["features"].get(0.0, {}).get(f"{s}:30s") for c in cis] for s in self.signal_names(p)}
            out[p] = self.attach_filter(p, dimension, usual, spread, [y - usual for y in ys], readings)
        return out

    def _feed_filters(self, person, signal, t):
        for (p, dim), filt in self.filters.items():
            if p != person or signal not in filt.sensors:
                continue
            key = (p, dim, signal)
            if t - self._fed.get(key, -math.inf) < FILTER_EVERY:
                continue
            vals = self.signals[(person, signal)].value(t)
            m, support = vals["30s"]
            filt.reading(t, signal, m, quality=weight_of(support))
            self._fed[key] = t

    # ------------------------------------------------------------------ the "why"
    def explain(self, person, t, dimension=None):
        """Rows for the "why" view at time t: for each signal its last raw reading, the person's normal, z, trust,
        and (with a fitted model for the dimension) its weights and contributions; plus the totals."""
        rows = []
        model, lags = self.models.get(dimension, (None, {}))
        pred = model.predict(person, self.features(person, t, lags)) if model else None
        w_usual, weights = model.weights(person) if model else (None, {})
        away = self.away(person, t)
        for s in self.signal_names(person):
            last = self.last.get((person, s), {})
            normal = last.get("normal")
            row = {"signal": s, "raw": last.get("raw"), "normal": normal[0] if normal else None,
                   "spread": normal[1] if normal else None, "z": last.get("z"), "quality": last.get("quality"),
                   "away_share": away["shares"].get(s), "lag": lags.get(s, 0.0)}
            if pred:
                feats = [f for f in pred["contributions"] if f.startswith(s + ":")]
                row["weights"] = {f.split(":", 1)[1]: weights[f] for f in feats}
                row["contribution"] = sum(pred["contributions"][f] for f in feats)
            rows.append(row)
        total = None
        if pred:
            total = {"value": pred["value"], "sd": pred["sd"], "usual": pred["usual"],
                     "fitted_to": pred["fitted_to"], "missing": pred["missing"]}
        filt = self.filters.get((person, dimension))
        return {"rows": rows, "away": away["score"], "estimate": total,
                "kalman": filt.estimate(t) if filt else None}


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return 0.0 if sxx <= 0 or syy <= 0 else sxy / math.sqrt(sxx * syy)
