# Experience Journal — Project Context

Status, measured values, decisions and history, so work can pick up where it left off (last: 2026-11-09). The design
itself is [docs/DESIGN.md](docs/DESIGN.md); the rules are [AGENTS.md](AGENTS.md).

## 1. What this is

A consented research project in behavioural analysis: a local-only journal of what each participant took in and how
they reacted, from any sensors they choose, fused into explainable estimates (DESIGN.md §1-2). Code is public; data
never leaves the project's computers.

## 2. Where it lives

| What | Where |
|---|---|
| This repository | `SingularityResearch/experience-journal` on GitHub (public, code only) |
| The face recognizer | `facial-recognition/` here, a git subtree of `SingularityResearch/facial-recognition` (public); changes go there first, then `git subtree pull --prefix=facial-recognition <its path or URL> main` |
| Participant data | `data/` (not in git), later the hub's SQLite database; the face recognizer's own data in its `data/` and `%APPDATA%\FaceLabels` |
| Python | 3.12; the fusion needs only numpy (Windows, macOS, Linux) |
| Face recognizer builds | its own repository's CI: tests and builds on Windows, macOS (Apple Silicon, 14+) and Linux (Ubuntu 22.04+); releases there (v1.9, 2026-11-10). Build steps: facial-recognition/face-recognizer/README.md, "Building the app" |
| Test builds | CI's `experience-journal-bundle` artifact (14 days); installed by `deploy/deploy_local.ps1` into `%LOCALAPPDATA%\ExperienceJournal\test` (builds, Start.cmd, its own face-root and face-home), Start menu **Experience Journal (test)** |

## 3. The fusion engine (`fusion/`)

Three layers (DESIGN.md §6): personal normals and trust-weighted windows (layer 1), the explained group model fitted
to check-ins (layer 2, the estimate shown), a Kalman filter over time (layer 3, kept only if it wins).

Values in the code, and whether they're measured:

| Value | Where | Status |
|---|---|---|
| `MIN_N` 120 readings, one per 30 s, last 5,000 | baselines.py | guess |
| `FREEZE_Z` 3, `MAX_PAUSE` 6 h | engine.py | guess |
| `Z_CLIP` 6 | engine.py | guess |
| `SETTLE` 120 s | engine.py | guess |
| `FILTER_EVERY` 600 s | engine.py | measured on simulated data: the 70% band held 54% at 30 s, 74-84% at 10 min |
| tau2 and noise | linear.py | chosen from the data by marginal likelihood at each fit |

## 4. Results so far (simulated people only)

Six simulated fortnights (2 people, 4 sensors, one irrelevant, 5 check-ins a day), 2026-11-09:

| | Error (1-7 scale) | 70% band holds |
|---|---|---|
| Layer 2, forward-chained | 0.54-0.65 | 68-86% |
| "Your average" | 0.88-1.07 | — |
| "Your last check-in" | 0.94-1.31 | — |
| Layer 2, live | 0.57-0.67 | 69-81% |
| Kalman, live | 0.59-0.67 | 79-84% |

The simulator follows the model's assumptions, so real data will do worse.

## 5. Decisions (keep honoring these)

- A research project where every participant consents per sensor, withdrawable; not a family-only tool
  (2026-11-09). Any sensor type through connectors; raw media only with that participant's consent for that sensor.
- Local only; the face recognizer never depends on the journal (it may offer an opt-in output the journal reads).
- Layer 2 is the estimate shown until layer 3 beats it on held-out weeks.
- Thresholds are marked measured or guess; results quoted say they're simulated until real sensors exist.
- Both repositories public, code only (2026-11-09).
- Test builds are pulled by the test computer, never pushed to it: no self-hosted runner on a public repository
  (2026-11-09). A test build never uses the owner's own library or private folder.

## 6. History

- 2026-11-09: plan and design; fusion engine on simulated data; the face recognizer brought in as a subtree.
- 2026-11-09, review: fusion fixes (spread floor and z clipping, per-signal learning pauses with a limit, late
  readings, settled check-in features, joint tau2/noise with the group average integrated out, missing sensors widen
  the band, traceable Why view, Kalman fed every 10 min, multi-seed tests); the project reframed as consented
  research with an open sensor set; face recognizer v1.9 (security and privacy fixes, export and forget per person,
  alert inbox with event types, timings and the evidence each alert measured).
- 2026-11-09: both repositories public; CI builds FaceRecognizer.exe (face recognizer) and the combined bundle
  (journal) after the checks pass; `deploy/deploy_local.ps1` installs green builds locally for hands-on testing.
- 2026-11-10: the face recognizer runs on macOS and Linux (per-system folders, browser fallback, CI on all three);
  tested on a real Ubuntu 26.04 laptop (window, camera, tracking, face mesh; mesh made easier to see) and released
  as v1.9 for Windows, macOS (not yet Apple-signed) and Linux.

## 7. Next

1. Hub phase 0 (DESIGN.md §8): SQLite schema with participants and per-sensor consent, devices, samples (with
   `(device, seq)` against duplicates) and media; the People and Sensors pages; export and delete per participant.
2. The face recognizer's opt-in signal output (in its own repository) and the journal's connector that reads it.
3. The engine rebuilt from stored samples, estimates stored with their contributions, the Why view from them.
4. Check-ins page and the first real data; then re-measure every guess above on held-out weeks.
5. Cross-platform test deploys (the in-app updater instead of `deploy_local.ps1` and its scheduled task), and the
   Apple signing secrets so the macOS build is signed and notarized.
