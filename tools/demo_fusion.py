"""
A look at the fusion on made-up people (fusion/simulate.py): two simulated weeks, then the "why" table for one
moment and how the layers compare. Run from the repository folder:  python tools/demo_fusion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fusion.engine import Fusion  # noqa: E402
from fusion.evaluate import forward_chain, prospective  # noqa: E402
from fusion.simulate import START, simulate  # noqa: E402


def main():
    def on_day(engine, d, day0):
        if d >= 5:
            engine.fit("energized", before=day0)
        if d == 7:
            engine.attach_filters("energized", before=day0)

    f = Fusion()
    print("Simulating 14 days for two made-up people ...")
    simulate(f, days=14, on_day=on_day)
    f.fit("energized")
    t = f.last[("A", "heart_rate")]["t"]
    ex = f.explain("A", t, "energized")
    est = ex["estimate"]
    print(f"\nPerson A, energized: {est['value']:.2f} (70% band +-{1.04 * est['sd']:.2f}), usual {est['usual']:.2f}, "
          f"away from normal {ex['away']:.2f}")
    print(f"{'signal':12s} {'raw':>8s} {'normal':>8s} {'spread':>7s} {'z':>6s} {'trust':>6s} {'lag':>5s} {'contrib':>8s}")
    for r in ex["rows"]:
        print(f"{r['signal']:12s} {r['raw']:8.2f} {r['normal']:8.2f} {r['spread']:7.2f} "
              f"{(r['z'] if r['z'] is not None else float('nan')):6.2f} {r['quality']:6.2f} {r['lag']:5.0f} "
              f"{r.get('contribution', 0.0):+8.2f}")
    print(f"{'':12s} usual {est['usual']:.2f} + contributions = {est['value']:.2f}")
    print("\nForward-chained (fit on earlier days, predict the next):")
    for name, m in forward_chain(f, "energized").items():
        cov = f", 70% band holds {m['coverage70']:.0%}" if m["coverage70"] is not None else ""
        print(f"  {name:20s} error {m['mae']:.2f}{cov}")
    print("Live, before each check-in (days 8-14):")
    for name, m in prospective(f, "energized", after=START + 7 * 86400).items():
        print(f"  {name:20s} error {m['mae']:.2f}, 70% band holds {m['coverage70']:.0%}")


if __name__ == "__main__":
    main()
