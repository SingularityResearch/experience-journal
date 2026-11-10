"""
Is the fusion any good? Measured the honest way (docs/DESIGN.md §6, "How we'd know it works").

- Forward chaining: for each day after the first few, fit on the earlier days only, predict that day's check-ins.
  Never shuffled: tomorrow mustn't help predict today.
- Against simple baselines: "your average" (the person's mean rating so far) and "your last check-in".
  A model that can't beat them says so.
- Calibration: a 70% band should hold about 70% of the check-ins.
- prospective(): the same metrics for what the engine's attached models predicted live, before each check-in
  (that's how layer 3, the Kalman filter, is compared with layer 2).
"""
import math
import time

Z70 = 1.0364             # a normal distribution holds 70% within this many standard deviations


def day_of(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def metrics(pairs):
    """pairs: [(rating, predicted, sd or None)] -> {n, mae, corr, coverage70}."""
    if not pairs:
        return {"n": 0, "mae": None, "corr": None, "coverage70": None}
    ys = [p[0] for p in pairs]
    ps = [p[1] for p in pairs]
    mae = sum(abs(y - p) for y, p in zip(ys, ps)) / len(ys)
    n = len(ys)
    my, mp = sum(ys) / n, sum(ps) / n
    sxy = sum((y - my) * (p - mp) for y, p in zip(ys, ps))
    sxx = sum((y - my) ** 2 for y in ys)
    spp = sum((p - mp) ** 2 for p in ps)
    corr = sxy / math.sqrt(sxx * spp) if sxx > 0 and spp > 0 else None
    with_sd = [(y, p, s) for y, p, s in pairs if s]
    cov = sum(abs(y - p) <= Z70 * s for y, p, s in with_sd) / len(with_sd) if with_sd else None
    return {"n": n, "mae": mae, "corr": corr, "coverage70": cov}


def forward_chain(engine, dimension, min_train_days=5, pool=True):
    """Fit layer 2 on each day's earlier days, predict that day. Returns {model name: metrics}."""
    cis = sorted((c for c in engine.checkins if dimension in c["ratings"]), key=lambda c: c["t"])
    days = sorted({day_of(c["t"]) for c in cis})
    results = {"fusion": [], "your average": [], "your last check-in": []}
    saved = engine.models.get(dimension)
    try:
        for d in days[min_train_days:]:
            start = min(c["t"] for c in cis if day_of(c["t"]) == d)
            model = engine.fit(dimension, before=start, pool=pool)
            lags = engine.models[dimension][1]
            history = {}
            for c in cis:
                if c["t"] < start:
                    history.setdefault(c["person"], []).append(c["ratings"][dimension])
            last = {p: h[-1] for p, h in history.items()}
            for c in (c for c in cis if day_of(c["t"]) == d):
                p, y = c["person"], c["ratings"][dimension]
                row = {}
                for s in engine.signal_names():
                    feats = c["features"].get(lags.get(s, 0.0), {})
                    for f in engine.feature_names():
                        if f.startswith(s + ":"):
                            row[f] = feats.get(f)
                pred = model.predict(p, row)
                results["fusion"].append((y, pred["value"], pred["sd"]))
                if p in history:
                    results["your average"].append((y, sum(history[p]) / len(history[p]), None))
                    results["your last check-in"].append((y, last[p], None))
                history.setdefault(p, []).append(y)          # later check-ins that day may use this one
                last[p] = y
    finally:                                                  # leave the engine's model as it was
        if saved is not None:
            engine.models[dimension] = saved
        else:
            engine.models.pop(dimension, None)
    return {name: metrics(pairs) for name, pairs in results.items()}


def prospective(engine, dimension, after=None):
    """Metrics of what each attached model predicted before each check-in (after a time, optionally)."""
    out = {}
    for e in engine.prediction_log:
        if e["dimension"] != dimension or (after is not None and e["t"] < after):
            continue
        for name, (value, sd) in e["predictions"].items():
            out.setdefault(name, []).append((e["rating"], value, sd))
    return {name: metrics(pairs) for name, pairs in out.items()}
