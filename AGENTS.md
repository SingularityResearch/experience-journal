# Experience Journal — guide for coding assistants and contributors

Read [docs/DESIGN.md](docs/DESIGN.md) first: principles, architecture, data model, fusion, phases.

## Rules that always apply

- A research project; every participant consents (informed, recorded per sensor, withdrawable at any time). Nothing
  is stored about anyone who hasn't consented. Every sensor is switchable per participant in the browser UI, and every
  participant can see, export and delete their own data.
- Any kind of sensor may be connected (webcam, imported photos and video, microphone and voice, wearables, phone,
  browser and content logs, other systems through a connector), each switched on per participant.
- Numbers by default: raw pictures, video or audio are kept only for a participant who opted into keeping that
  sensor's raw data (recorded in their consent, shown on the Sensors page); content logs keep titles, addresses, topics
  and times.
- Local only: no cloud services, accounts or telemetry. The hub accepts sensor data only from paired devices on the
  local network, and its browser UI only from this computer.
- Never commit anything from `data/` or any personal detail (names, paths, accounts). A fresh copy starts empty.
- Every estimate shows how it was reached (sensor values, personal normal, weight, contribution, quality). Name lines
  by what they were fitted to; describe signals, not feelings, unless check-ins back it up.
- Measured before trusted: thresholds and weights come from our own data and are marked as measured or as guesses.
- The subliminal work lives only in `subliminal/` (and the Lab page that runs it): separate opt-in per person, off by
  default, every session logged and visible to that participant, blinded active/sham arms with outcomes analysed before
  unblinding. Nothing else imports it.
- The face recognizer is a separate, standalone project; integration is an opt-in on its side and must never make it
  depend on this one.

## Development

Python 3.12 (`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`), standard library server, SQLite, plain HTML/JS.
Tests from the start: `python -m pytest tests -q` and `python -m ruff check .` (CI runs both); browser code later with
`node --test tests/*.test.js`.

- `fusion/` — the fusion engine (DESIGN.md §6): `baselines.py` (personal normals), `windows.py` (trust-weighted
  multi-window averages, lags), `away.py` (away-from-normal score), `linear.py` (group Bayesian model, exact
  contributions), `kalman.py` (layer 3, optional: used only if it beats layer 2), `engine.py` (readings in, explained
  estimates out; logs live predictions), `evaluate.py` (forward chaining, baselines, calibration), `simulate.py`
  (made-up people for tests; never a claim about real people).
- `tools/demo_fusion.py` — prints a "why" table and the layer comparison on simulated data.
- Results quoted in DESIGN.md are on simulated data until real sensors exist; say so whenever they're quoted.
- Git remote: `origin` (public GitHub repository, code only); push only with the owner's go-ahead. Being public,
  nothing personal may ever be committed: no participant data, names, paths, accounts or keys.
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md): status, measured values, decisions and history; update it with each
  change that matters, like the face recognizer's.

## The face recognizer inside this repository (`facial-recognition/`)

- A git subtree of the standalone repository SingularityResearch/facial-recognition (public, code only), with its
  history. Its own guide, [facial-recognition/AGENTS.md](facial-recognition/AGENTS.md), applies to everything in that
  folder (measured thresholds, privacy rules, its tests).
- It must keep working on its own: nothing in it may import or require journal code. The journal reads from it (its
  signals, through an opt-in on its side), never the other way round.
- Make changes to it in its own repository first, then bring them here:
  `git subtree pull --prefix=facial-recognition <path or URL of facial-recognition> main`. A change made here first
  can be sent back with `git subtree push`, but keep its public repository free of anything journal-specific or personal.
- Its models are Git LFS files here too (about 400 MB); its `data/` is never committed (both .gitignore files).
- CI runs its checks as a second job (Node tests, ruff, pytest, in `facial-recognition/face-recognizer`).
