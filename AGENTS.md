# Experience Journal — guide for coding assistants and contributors

Read [docs/DESIGN.md](docs/DESIGN.md) first: principles, architecture, data model, fusion, phases.

## Rules that always apply

- Family only, everyone consenting; nothing is stored about anyone not enrolled. Every sensor is switchable per person
  in the browser UI, and every person can see, export and delete their own data.
- Local only: no cloud services, accounts or telemetry. The hub accepts sensor data only from paired devices on the
  home network, and its browser UI only from this computer.
- Never commit anything from `data/` or any personal detail (names, paths, accounts). A fresh copy starts empty.
- Numbers by default: no pictures or audio stored; content logs keep titles, addresses, topics and times.
- Every estimate shows how it was reached (sensor values, personal normal, weight, contribution, quality). Name lines
  by what they were fitted to; describe signals, not feelings, unless check-ins back it up.
- Measured before trusted: thresholds and weights come from our own data and are marked as measured or as guesses.
- The subliminal work lives only in `subliminal/` (and the Lab page that runs it): separate opt-in per person, off by
  default, every session logged and visible to that person, blinded active/sham arms with outcomes analysed before
  unblinding. Nothing else imports it.
- The face recognizer is a separate, standalone project; integration is an opt-in on its side and must never make it
  depend on this one.

## Development

Python 3.12 (`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`), standard library server, SQLite, plain HTML/JS.
Tests from the start: `python -m pytest tests -q` and `python -m ruff check .` (CI runs both); browser code later with
`node --test tests/*.test.js`.

- `fusion/` — the fusion engine (DESIGN.md §6): `baselines.py` (personal normals), `windows.py` (trust-weighted
  multi-window averages, lags), `away.py` (away-from-normal score), `linear.py` (family Bayesian model, exact
  contributions), `kalman.py` (layer 3, optional: used only if it beats layer 2), `engine.py` (readings in, explained
  estimates out; logs live predictions), `evaluate.py` (forward chaining, baselines, calibration), `simulate.py`
  (made-up people for tests; never a claim about real people).
- `tools/demo_fusion.py` — prints a "why" table and the layer comparison on simulated data.
- Results quoted in DESIGN.md are on simulated data until real sensors exist; say so whenever they're quoted.
- Git remote: `origin` (private GitHub repository); push only with the owner's go-ahead.
