"""
The explainable fused estimate, fitted to check-ins: layer 2 of the fusion (docs/DESIGN.md §6).

For one dimension (for example "energized", rated 1-7), a person's rating is modelled as
    rating = their usual + sum over features of (weight x feature) + noise,
where the features are smoothed z-scores (0 = their normal). Each feature's contribution is weight x value, and the
contributions plus "their usual" add up exactly to the estimate.

Fitted as one group model (Bayesian, hierarchical): each person's weights are the group's average weights plus
their own departure from them, which is only as large as their own check-ins justify. With few check-ins a person
gets sensible weights instead of wild ones, a new person starts from the group's, and every estimate comes with an
honest spread: the leftover noise, the uncertainty in the person's weights, and the uncertainty in the group's
average itself (two or three people say little about a "group average", and the spread shows it). For each person,
the group average they are pulled toward is the one the *other* people's check-ins give, so nobody's own data
counts twice. `pool=False` fits each person alone (plain Bayesian ridge), for comparison.

Features are scaled to unit spread (over the check-ins where they were present) before fitting, so the prior treats
every feature alike: a 10-minute window varies far less than a 30-second one, and unscaled it could take a large
weight that changes almost nothing. Weights are reported back on the original scale, so weight x value is still
exactly each feature's contribution.

A feature missing at a check-in (NaN in X, None in predict) counts as 0 (at normal) in the estimate, and its
uncertainty is added to the band: how much it still varies given the features that are present (from their
covariance over the check-ins), times its weight. The band is wider when a sensor is silent, never narrower.

How strongly people are pulled toward the group (tau2) and the leftover noise (sigma2) are chosen together by
marginal likelihood (the evidence the data give for each setting, with the group average integrated out), from a
grid. Everything is numpy; sizes are small (hundreds of check-ins, tens of features).
"""
import math

import numpy as np

TAU2_GRID = (0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0)   # prior variance of a person's weights around the group's
SIGMA2_FACTORS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2)   # leftover noise grid, x the pooled fit's
SIGMA2_FLOOR = 0.05      # leftover noise never below this (ratings are whole numbers: rounding alone is ~0.08)
INTERCEPT_VAR = 4.0      # prior variance of a person's usual rating around the group's (1-7 scale: +-2)
# The group average itself (a guess, weakly informative): usual around the mean rating with variance 25, each
# weight around 0 with variance 1 (on the unit-spread scale: one typical swing moving the rating by about 1 point).
GROUP_INTERCEPT_VAR = 25.0
GROUP_WEIGHT_VAR = 1.0


def _with_intercept(X):
    X = np.asarray(X, float)
    return np.hstack([np.ones((X.shape[0], 1)), X])


def _posterior(X, y, m0, S0, sigma2):
    """Gaussian posterior of the weights with prior N(m0, S0) (S0 a full matrix): (mean, covariance)."""
    S0i = np.linalg.inv(S0)
    cov = np.linalg.inv(X.T @ X / sigma2 + S0i)
    cov = (cov + cov.T) / 2
    mean = cov @ (X.T @ y / sigma2 + S0i @ m0)
    return mean, cov


class _Stats:
    """One person's check-ins reduced to what the model needs: X'X, X'y, y'y, n."""

    def __init__(self, X, y):
        self.XX, self.Xy, self.yy, self.n = X.T @ X, X.T @ y, float(y @ y), len(y)


def _marginal(st, S0_diag, sigma2):
    """For y ~ N(X m, C) with C = sigma2 I + X S0 X^T (a person's weights integrated out), using only k x k
    matrices (Woodbury): returns (X'C^-1 X, X'C^-1 y, a function m -> -0.5 (r'C^-1 r) with r = y - X m, log det C)."""
    k = len(S0_diag)
    M = np.diag(sigma2 / S0_diag) + st.XX                  # sigma2 S0^-1 + X'X
    Mi = np.linalg.inv(M)
    XCX = (st.XX - st.XX @ Mi @ st.XX) / sigma2
    XCy = (st.Xy - st.XX @ Mi @ st.Xy) / sigma2
    logdet = st.n * math.log(sigma2) + np.linalg.slogdet(np.eye(k) + (S0_diag[:, None] * st.XX) / sigma2)[1]

    def quad(m):
        Xr = st.Xy - st.XX @ m
        rr = st.yy - 2 * m @ st.Xy + m @ st.XX @ m
        return -0.5 * (rr - Xr @ Mi @ Xr) / sigma2
    return XCX, XCy, quad, logdet


def _log_evidence(st, m0, S0_diag, sigma2):
    """log N(y; X m0, sigma2 I + X S0 X^T): how well this prior explains one person's ratings."""
    _, _, quad, logdet = _marginal(st, S0_diag, sigma2)
    return quad(m0) - 0.5 * (logdet + st.n * math.log(2 * math.pi))


def _pairwise_cov(Z):
    """Covariance of the columns of Z (NaN = missing), each pair over the rows where both are present; made positive
    semi-definite. A column never present gets variance 1 (the unit-spread scale) and no covariance."""
    k = Z.shape[1]
    S = np.eye(k)
    ok = np.isfinite(Z)
    for i in range(k):
        for j in range(i, k):
            both = ok[:, i] & ok[:, j]
            if both.sum() > 2:
                a, b = Z[both, i], Z[both, j]
                S[i, j] = S[j, i] = float(((a - a.mean()) * (b - b.mean())).mean())
    vals, vecs = np.linalg.eigh(S)
    return (vecs * np.clip(vals, 0.0, None)) @ vecs.T


class GroupLinear:
    """One dimension's model for the whole group. fit({person: (X, y)}), then predict(person, x)."""

    def __init__(self, features, pool=True, tau2_grid=TAU2_GRID, intercept_var=INTERCEPT_VAR):
        self.features = list(features)
        self.pool = pool
        self.tau2_grid = tau2_grid
        self.intercept_var = intercept_var
        self.people = {}             # person -> (mean, cov) of their usual + weights (scaled features)
        self.group = None           # the group's average (intercept + weights), scaled features
        self.group_cov = None       # its uncertainty
        self.sigma2 = None
        self.tau2 = None
        self.evidence = None         # log marginal likelihood of the chosen (tau2, sigma2)
        self.scale = None            # each feature's spread over the check-ins where it was present
        self.feature_cov = None      # covariance of the scaled features (pairs where both were present)

    def _prior(self, tau2):
        k = len(self.features)
        return np.r_[self.intercept_var, np.full(k, tau2)]

    def _group_fit(self, stats, S0_diag, sigma2, ymean):
        """The group average with everyone's own departures integrated out. Returns (mean, cov, log evidence,
        {person: (A_p, b_p)}, A, b) where A = prior precision + sum of A_p, and b likewise."""
        k1 = len(S0_diag)
        F0 = np.r_[GROUP_INTERCEPT_VAR, np.full(k1 - 1, GROUP_WEIGHT_VAR)]
        mF = np.r_[ymean, np.zeros(k1 - 1)]
        A, b = np.diag(1.0 / F0), mF / F0
        parts, quads, ev = {}, {}, 0.0
        for p, st in stats.items():
            Ap, bp, quads[p], logdet = _marginal(st, S0_diag, sigma2)
            parts[p] = (Ap, bp)
            A, b = A + Ap, b + bp
            ev -= 0.5 * (logdet + st.n * math.log(2 * math.pi))
        cov = np.linalg.inv(A)
        cov = (cov + cov.T) / 2
        mean = cov @ b
        # log p(y) = sum_p log N(y_p; X_p mean, C_p) + log N(mean; mF, F0) - log N(mean; mean, cov)
        ev += sum(q(mean) for q in quads.values())
        d = mean - mF
        ev += -0.5 * (d @ (d / F0) + np.log(F0).sum())
        ev += 0.5 * np.linalg.slogdet(cov)[1]
        return mean, cov, ev, parts, A, b

    def fit(self, data):
        """data: {person: (X n x k, y n)} with the columns in self.features' order; NaN = missing."""
        data = {p: (np.asarray(X, float).reshape(len(y), -1), np.asarray(y, float)) for p, (X, y) in data.items()
                if len(y)}
        if not data:
            raise ValueError("no check-ins to fit")
        raw = np.vstack([X for X, _ in data.values()])
        with np.errstate(invalid="ignore"):
            present = np.isfinite(raw).sum(axis=0)
            sd = np.array([np.nanstd(raw[:, j]) if present[j] > 1 else 0.0 for j in range(raw.shape[1])])
        self.scale = np.where(sd > 1e-9, sd, 1.0)
        self.feature_cov = _pairwise_cov(raw / self.scale)
        data = {p: (_with_intercept(np.nan_to_num(X / self.scale, nan=0.0)), y) for p, (X, y) in data.items()}
        allX = np.vstack([X for X, _ in data.values()])
        ally = np.concatenate([y for _, y in data.values()])
        k1 = allX.shape[1]
        ymean = float(ally.mean())
        # a starting point for the noise: what one shared fit for everyone leaves unexplained
        lam = np.r_[1e-6, np.ones(k1 - 1)]
        pooled = np.linalg.solve(allX.T @ allX + np.diag(lam), allX.T @ ally)
        resid = ally - allX @ pooled
        s2_pooled = max(float(resid @ resid) / max(1, len(ally) - k1), SIGMA2_FLOOR)
        sigma2_grid = sorted({max(SIGMA2_FLOOR, f * s2_pooled) for f in SIGMA2_FACTORS})
        stats = {p: _Stats(X, y) for p, (X, y) in data.items()}

        best = None
        for tau2 in self.tau2_grid:
            S0 = self._prior(tau2)
            for sigma2 in sigma2_grid:
                if self.pool:
                    ev = self._group_fit(stats, S0, sigma2, ymean)[2]
                else:
                    m0 = np.r_[pooled[0], np.zeros(k1 - 1)]
                    ev = sum(_log_evidence(st, m0, S0, sigma2) for st in stats.values())
                if best is None or ev > best[0]:
                    best = (ev, tau2, sigma2)
        self.evidence, self.tau2, self.sigma2 = best
        S0 = self._prior(self.tau2)
        if self.pool:
            fam, fam_cov, _, parts, A, b = self._group_fit(stats, S0, self.sigma2, ymean)
            self.group, self.group_cov = fam, fam_cov
            self.people = {}
            for p, (X, y) in data.items():
                # the group average from everyone else's check-ins: this person's own data counts once
                Ap, bp = parts[p]
                cov_o = np.linalg.inv(A - Ap)
                mean_o = cov_o @ (b - bp)
                self.people[p] = _posterior(X, y, mean_o, np.diag(S0) + cov_o, self.sigma2)
        else:
            self.group = np.r_[pooled[0], np.zeros(k1 - 1)]
            self.group_cov = np.zeros((k1, k1))
            self.people = {p: _posterior(X, y, self.group, np.diag(S0), self.sigma2) for p, (X, y) in data.items()}
        return self

    def _person(self, person):
        if person in self.people:
            return (*self.people[person], "own")
        return self.group, np.diag(self._prior(self.tau2)) + self.group_cov, "group"

    def weights(self, person):
        """Their usual, and {feature: weight} on the features' own scale (the group's for someone new)."""
        mean, _, _ = self._person(person)
        return float(mean[0]), dict(zip(self.features, map(float, mean[1:] / self.scale)))

    def importance(self, person):
        """{feature: how far a typical swing (one spread) of it moves this person's estimate}: the weights on the
        common scale, comparable across features (the raw weights aren't: their units differ)."""
        mean, _, _ = self._person(person)
        return dict(zip(self.features, map(lambda w: abs(float(w)), mean[1:])))

    def uncertainty(self, person):
        """{feature: standard deviation of its weight} on the common scale (as importance()): a weight within about
        two of these of 0 isn't distinguishable from "no effect" yet."""
        _, cov, _ = self._person(person)
        return dict(zip(self.features, map(float, np.sqrt(np.diag(cov)[1:]))))

    def predict(self, person, x):
        """x: {feature: value} (missing features count as 0 = at normal, are listed as missing, and widen the band).
        Returns {"value", "sd", "usual", "contributions": {feature: weight x value}, "missing": [...],
        "fitted_to": "own" | "group"}; usual + sum(contributions) == value exactly."""
        if self.group is None:
            raise ValueError("fit() first")
        mean, cov, fitted = self._person(person)
        missing = [f for f in self.features if x.get(f) is None]
        vec = np.array([0.0 if x.get(f) is None else float(x[f]) for f in self.features]) / self.scale
        xv = np.r_[1.0, vec]
        value = float(xv @ mean)
        var = self.sigma2 + float(xv @ cov @ xv)
        # a missing feature is unknown, not 0: what it can still do given the present ones, times its weight
        # (and that weight's own uncertainty), adds to the spread
        if missing:
            mi = [self.features.index(f) for f in missing]
            oi = [j for j in range(len(self.features)) if j not in mi]
            S = self.feature_cov
            Sc = S[np.ix_(mi, mi)]
            if oi:
                So = S[np.ix_(oi, oi)] + 1e-6 * np.eye(len(oi))
                Smo = S[np.ix_(mi, oi)]
                Sc = Sc - Smo @ np.linalg.solve(So, Smo.T)
            Sc = (Sc + Sc.T) / 2
            wm = mean[1:][mi]
            var += max(0.0, float(wm @ Sc @ wm + np.trace(Sc @ cov[1:, 1:][np.ix_(mi, mi)])))
        contributions = {f: float(w * v) for f, w, v in zip(self.features, mean[1:], vec)}   # scaled x scaled
        return {"value": value, "sd": math.sqrt(var), "usual": float(mean[0]), "contributions": contributions,
                "missing": missing, "fitted_to": fitted}
