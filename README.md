# Experience Journal

A private, local-only journal of what each of us took in and how we reacted, measured by the sensors we choose on
our own devices, fused into explainable estimates, daily reports and (later) patterns, predictions, coaching and
training. For our family only, everyone consenting; nothing leaves our home network.

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
python -m pytest tests -q            # about 25 s: includes a simulated fortnight
```

Related: the face recognizer (separate, standalone repository `facial-recognition`) can send its numbers here.
