"""
"Away from your normal": the fused score before there are any check-ins (docs/DESIGN.md §6, layer 2).

The score is the trust-weighted root mean square of the signals' smoothed z-scores (by default their 10-minute
windows): 0 is exactly your normal; 1 means the signals have sat, on average, one typical spread of a single reading
away from it for the whole window, which is already unusual (the average of ten minutes of ordinary readings is much
closer to 0 than a single reading is). It has no direction: it says how unusual the moment is, not what it means.
Each signal's contribution is exact: the contributions add up to score², so each signal's share of the score is
its contribution / score².
"""
import math


def away_from_normal(readings):
    """readings: {signal: (z, weight)} with weight = trust x support (0 or less: left out).
    Returns {"score", "contributions": {signal: part of score²}, "shares": {signal: 0-1}, "signals": n used}."""
    used = {s: (z, w) for s, (z, w) in readings.items() if z is not None and w > 0 and math.isfinite(z)}
    total_w = sum(w for _, w in used.values())
    if not used or total_w <= 0:
        return {"score": None, "contributions": {}, "shares": {}, "signals": 0}
    contributions = {s: w * z * z / total_w for s, (z, w) in used.items()}
    score2 = sum(contributions.values())
    shares = {s: (c / score2 if score2 > 0 else 0.0) for s, c in contributions.items()}
    return {"score": math.sqrt(score2), "contributions": contributions, "shares": shares, "signals": len(used)}
