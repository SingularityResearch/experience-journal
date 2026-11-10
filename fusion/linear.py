"""
The explainable fused estimate, fitted to check-ins: layer 2 of the fusion (docs/DESIGN.md §6).

For one dimension (for example "energized", rated 1-7), a person's rating is modelled as
    rating = their usual + sum over features of (weight x feature) + noise,
where the features are smoothed z-scores (0 = their normal). Each feature's contribution is weight x value, and the
contributions plus "their usual" add up exactly to the estimate.

Fitted as one family model (Bayesian, hierarchical): each person's weights start at the family's average weights
and move away only as far as their own check-ins justify. With few check-ins a person gets sensible weights instead
of wild ones, a new person starts from the family's, and every estimate comes with an honest spread (from the
uncertainty in the weights and the leftover noise). `pool=False` fits each person alone (plain Bayesian ridge),
for comparison.

Features are scaled to unit spread (over the whole family's check-ins) before fitting, so the prior treats every
feature alike: a 10-minute window varies far less than a 30-second one, and unscaled it could take a large weight
that changes almost nothing. Weights are reported back on the original scale, so weight x value is still exactly
each feature's contribution.

How strongly people are pulled toward the family (tau2) is chosen by marginal likelihood, the evidence the data
give for each setting, from a grid. Everything is numpy; sizes are small (hundreds of check-ins, tens of features).
"""
import math

import numpy as np

TAU2_GRID = (0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0)   # prior variance of weights around the family's
INTERCEPT_VAR = 4.0      # prior variance of a person's usual rating around the family's (1-7 scale: +-2)


def _with_intercept(X):
    X = np.asarray(X, float)
    return np.hstack([np.ones((X.shape[0], 1)), X])


def _posterior(X, y, m0, S0_diag, sigma2):
    """Gaussian posterior of the weights: (mean, covariance)."""
    prec = X.T @ X / sigma2 + np.diag(1.0 / S0_diag)
    cov = np.linalg.inv(prec)
    mean = cov @ (X.T @ y / sigma2 + m0 / S0_diag)
    return mean, cov


def _log_evidence(X, y, m0, S0_diag, sigma2):
    """log N(y; X m0, sigma2 I + X S0 X^T): how well this prior explains the person's ratings."""
    C = sigma2 * np.eye(len(y)) + (X * S0_diag) @ X.T
    r = y - X @ m0
    sign, logdet = np.linalg.slogdet(C)
    return -0.5 * (r @ np.linalg.solve(C, r) + logdet + len(y) * math.log(2 * math.pi))


class FamilyLinear:
    """One dimension's model for the whole family. fit({person: (X, y)}), then predict(person, x)."""

    def __init__(self, features, pool=True, tau2_grid=TAU2_GRID, intercept_var=INTERCEPT_VAR):
        self.features = list(features)
        self.pool = pool
        self.tau2_grid = tau2_grid
        self.intercept_var = intercept_var
        self.people = {}             # person -> (mean, cov)
        self.family = None           # prior mean (intercept + weights)
        self.sigma2 = None
        self.tau2 = None
        self.scale = None            # each feature's spread over the family's check-ins

    def _prior(self, tau2):
        k = len(self.features)
        return np.r_[self.intercept_var, np.full(k, tau2)]

    def fit(self, data):
        """data: {person: (X n x k, y n)} with the columns in self.features' order."""
        data = {p: (np.asarray(X, float).reshape(len(y), -1), np.asarray(y, float)) for p, (X, y) in data.items()
                if len(y)}
        if not data:
            raise ValueError("no check-ins to fit")
        sd = np.vstack([X for X, _ in data.values()]).std(axis=0)
        self.scale = np.where(sd > 1e-9, sd, 1.0)
        data = {p: (_with_intercept(X / self.scale), y) for p, (X, y) in data.items()}
        allX = np.vstack([X for X, _ in data.values()])
        ally = np.concatenate([y for _, y in data.values()])
        k1 = allX.shape[1]
        # the family's average weights: everyone's check-ins together, lightly held toward zero
        lam = np.r_[1e-6, np.ones(k1 - 1)]
        fam = np.linalg.solve(allX.T @ allX + np.diag(lam), allX.T @ ally)
        if not self.pool:
            fam = np.r_[fam[0], np.zeros(k1 - 1)]
        self.family = fam
        # leftover noise: what the family fit can't explain (a floor keeps it from collapsing on tiny data)
        resid = ally - allX @ fam
        self.sigma2 = max(float(resid @ resid) / max(1, len(ally) - k1), 0.05)
        best = None
        for tau2 in self.tau2_grid:
            S0 = self._prior(tau2)
            ev = sum(_log_evidence(X, y, fam, S0, self.sigma2) for X, y in data.values())
            if best is None or ev > best[0]:
                best = (ev, tau2)
        self.tau2 = best[1]
        S0 = self._prior(self.tau2)
        self.people = {p: _posterior(X, y, fam, S0, self.sigma2) for p, (X, y) in data.items()}
        # with the people's own weights, re-estimate the noise once
        res = [y - X @ self.people[p][0] for p, (X, y) in data.items()]
        r = np.concatenate(res)
        self.sigma2 = max(float(r @ r) / max(1, len(r) - k1), 0.05)
        self.people = {p: _posterior(X, y, fam, S0, self.sigma2) for p, (X, y) in data.items()}
        return self

    def weights(self, person):
        """Their usual, and {feature: weight} on the features' own scale (the family's for someone new)."""
        mean, _ = self.people.get(person, (self.family, None))
        return float(mean[0]), dict(zip(self.features, map(float, mean[1:] / self.scale)))

    def importance(self, person):
        """{feature: how far a typical swing (one spread) of it moves this person's estimate}: the weights on the
        common scale, comparable across features (the raw weights aren't: their units differ)."""
        mean, _ = self.people.get(person, (self.family, None))
        return dict(zip(self.features, map(lambda w: abs(float(w)), mean[1:])))

    def predict(self, person, x):
        """x: {feature: value} (missing features count as 0 = at normal, and are listed as missing).
        Returns {"value", "sd", "usual", "contributions": {feature: weight x value}, "missing": [...],
        "fitted_to": "own" | "family"}; usual + sum(contributions) == value exactly."""
        if self.family is None:
            raise ValueError("fit() first")
        if person in self.people:
            mean, cov = self.people[person]
            fitted = "own"
        else:
            mean, cov = self.family, np.diag(self._prior(self.tau2))
            fitted = "family"
        vec = np.array([x.get(f, 0.0) if x.get(f) is not None else 0.0 for f in self.features]) / self.scale
        xv = np.r_[1.0, vec]
        value = float(xv @ mean)
        sd = math.sqrt(self.sigma2 + float(xv @ cov @ xv))
        contributions = {f: float(w * v) for f, w, v in zip(self.features, mean[1:], vec)}   # scaled x scaled
        missing = [f for f in self.features if x.get(f) is None]
        return {"value": value, "sd": sd, "usual": float(mean[0]), "contributions": contributions,
                "missing": missing, "fitted_to": fitted}
