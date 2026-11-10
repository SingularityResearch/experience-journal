# Experience Journal

A local-only research journal in behavioural analysis: what each participant took in (read, watched, heard, did)
and how they reacted, measured by any sensors they choose (webcam, imported images and video, voice, wearables,
phone, browser, other systems through connectors), fused into explainable estimates, daily reports and, later,
patterns, predictions, coaching and training. Every participant consents, per sensor; their data stays on the
project's own computers and local network. This repository holds the code only: no participant data, ever.

Status: the fusion engine (`fusion/`) is built and tested on **simulated** people; the face recognizer (its first
sensor source) runs on its own; the hub, the other sensors and the browser UI come next. The design, principles and
phased plan are in [docs/DESIGN.md](docs/DESIGN.md).

## Goals

- Measure reactions with every sensor a participant chooses, on their own scale (their personal normal), and fuse
  them into a few dimensions (energized, pleasant, engaged, loaded).
- Show how every estimate was reached: each sensor's reading, its normal, weight, contribution and trust.
- Treat every signal, weight, prediction and intervention as a hypothesis until held-out data says it works, and
  report the nulls.
- Keep participants in control: consent per sensor, see everything, switch anything off, export or delete it.

## What's in the repo

| Folder | What |
|---|---|
| `fusion/` | the fusion engine: personal normals, multi-window signals, explainable group model, Kalman layer, evaluation |
| `facial-recognition/` | the face recognizer (FaceRecognizer.exe: live tracker, labeling tool, alerts, Settings), the first sensor source; a copy of [its own public repository](https://github.com/SingularityResearch/facial-recognition), kept in step with `git subtree pull` |
| `docs/` | the design and plan |
| `tools/`, `tests/` | the fusion demo and tests |
| `deploy/` | the test build's launchers and `deploy_local.ps1`, which installs green builds on a test computer |

The face recognizer works on its own and never depends on this repository: see
[facial-recognition/README.md](facial-recognition/README.md).

## Key decisions, and why

- **Consent first.** A research project where every participant consents per sensor and can withdraw; nothing is
  stored about anyone who hasn't consented (other faces and voices are ignored).
- **Local only.** No cloud services, accounts or telemetry; the hub accepts data only from paired devices on the
  local network and shows its pages only on its own computer.
- **Numbers by default.** Raw pictures, video or audio are kept only for a participant who opted into it for that
  sensor.
- **Explainable fusion before clever fusion.** A Bayesian linear model whose contributions add up exactly is the
  estimate shown; a Kalman filter is kept only if it beats it on held-out weeks (so far it doesn't).
- **Honest evaluation.** Forward chaining (fit on earlier days, predict the next), simple baselines, calibration of
  the bands, several random seeds.

## Current status and limits

- All fusion results are on simulated people (`fusion/simulate.py`), whose sensors follow the model's own
  assumptions; real data will do worse. On six simulated fortnights the explained estimate's error is 0.54-0.65 on a
  1-7 scale against 0.88-1.07 for "your average", and its 70% band holds 68-86%.
- Thresholds marked as guesses in the code (pause lengths, clipping, settling delay) are not yet measured.
- Not built yet: the hub, its database and pages, the sensor connectors other than the face recognizer.

## Try the fusion

```
python -m pip install -r requirements.txt
python tools/demo_fusion.py          # two simulated weeks, a "why" table, and how the layers compare
```

## Checks

```
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest tests -q            # about 10 s: includes three simulated fortnights
```

CI runs these, and the face recognizer's own checks, on every push and pull request.

## Test builds (human in the loop)

Once every check passes, CI builds the combined application on Windows: `FaceRecognizer.exe` (from
`facial-recognition/`, with its own `build_exe.py`), the journal's code, launchers, `BUILD-INFO.json` and
`SHA256SUMS.txt`, as the run's **experience-journal-bundle** artifact (kept 14 days).

On a test computer, [deploy/deploy_local.ps1](deploy/deploy_local.ps1) installs the newest green build of `main`.
It pulls the build (GitHub never reaches into the computer), checks every file's SHA-256 and the commit, and
keeps the last 3 builds. The test app gets its own models and data folders, so it never touches your own library.
It needs the GitHub CLI, signed in.

```
powershell -ExecutionPolicy Bypass -File deploy\deploy_local.ps1 -Launch          # install the newest build and start it
powershell -ExecutionPolicy Bypass -File deploy\deploy_local.ps1 -SeedFrom <face-recognizer folder>   # copy models and a library into the test folders, once
powershell -ExecutionPolicy Bypass -File deploy\deploy_local.ps1 -Install         # check every 10 minutes, notify per new build
powershell -ExecutionPolicy Bypass -File deploy\deploy_local.ps1 -Uninstall       # stop checking
```

Start the installed build from the Start menu (**Experience Journal (test)**). A running test copy is never
stopped: the next start uses the new build.

## Participant data stays on your computers

Nothing a sensor records is ever in this repository: `data/`, databases and the face recognizer's `data/` are in
`.gitignore`, and a fresh copy starts empty. Encrypt the hub's drive (BitLocker on Windows).

## License

Apache License 2.0 ([LICENSE](LICENSE)), as the face recognizer. Third-party models used by the face recognizer
keep their own licenses: see [facial-recognition/README.md](facial-recognition/README.md).

## Documentation map

- [docs/DESIGN.md](docs/DESIGN.md): principles, architecture, data model, fusion, phases
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md): status, measured values, decisions, history and open items
- [AGENTS.md](AGENTS.md): rules, layout and how to test, for coding assistants and contributors ([CLAUDE.md](CLAUDE.md) reads it)
- [facial-recognition/README.md](facial-recognition/README.md): the face recognizer
