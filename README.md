# Experience Journal

A private, local-only research journal of what each participant took in and how they reacted, measured by any
sensors they choose (webcam, imported images, voice, wearables, browser, other connected systems), fused into
explainable estimates, daily reports and (later) patterns, predictions, coaching and training. Every participant
consents; nothing leaves the local network.

Status: the fusion engine (`fusion/`) is built and tested on simulated people; sensors, the hub and the browser UI
come next. The design, principles and phased plan are in [docs/DESIGN.md](docs/DESIGN.md).

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

## What's in this repository

| Folder | What |
|---|---|
| `fusion/` | the fusion engine: personal normals, multi-window signals, explainable group model, Kalman layer, evaluation |
| `facial-recognition/` | the face recognizer (FaceRecognizer.exe: live tracker, labeling tool, Settings), the journal's first sensor source; a copy of its own repository, kept in step with `git subtree pull` |
| `docs/` | the design and plan |
| `tools/`, `tests/` | the fusion demo and tests |

The face recognizer still works on its own: see [facial-recognition/README.md](facial-recognition/README.md) and
[facial-recognition/face-recognizer/README.md](facial-recognition/face-recognizer/README.md).
