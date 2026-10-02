"""
Tunes all of the planner's settings (planner.TUNABLE) by playing thousands of fake games, and writes the
best ones to tuned.py (which the planner loads). Not part of the app.

The fast fake games and the score are in ../practice.py (the app uses them to practice while it plays).

    python tests/tune.py check                 # play the current settings once, see the speed
    python tests/tune.py tune [generations]    # tune (uses every CPU core), writes tuned.py
    python tests/tune.py compare               # tuned.py vs the hand-picked values, on games it never saw

Needs: pip install cma
"""

import math
import os
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

import planner  # noqa: E402
from practice import SCENARIOS, play, score, to_values, _job  # noqa: E402,F401


def _base_values():
    """The hand-picked values (planner.py itself, without tuned.py)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("planner_plain", os.path.join(BOT, "planner.py"))
    src = open(os.path.join(BOT, "planner.py")).read().replace("from tuned import TUNED", "raise ImportError")
    mod = importlib.util.module_from_spec(spec)
    exec(compile(src, "planner_plain", "exec"), mod.__dict__)
    return {n: mod.get_setting(n) for n in mod.TUNABLE}


def write_tuned(values, note):
    lines = ['"""Planner settings tuned by tests/tune.py (fake game, %s). Delete this file to use the',
             'hand-picked values in planner.py."""', "", "TUNED = {"]
    lines[0] = lines[0] % note
    for n in planner.TUNABLE:
        lines.append(f"    {n!r}: {values[n]:.4g},")
    lines.append("}")
    with open(os.path.join(BOT, "tuned.py"), "w") as f:
        f.write("\n".join(lines) + "\n")


STATE = os.path.join(HERE, ".tune_state.pkl")  # so a restart carries on where it was


def tune(generations=30):
    import pickle
    import cma
    base = {n: planner.get_setting(n) for n in planner.TUNABLE}  # search around the current values (tuned.py)
    pool = Pool(os.cpu_count())
    check = [5000 + i for i in range(6)]
    if os.path.exists(STATE):
        with open(STATE, "rb") as f:
            es, gen0, best, best_x, f_base = pickle.load(f)
        print(f"carrying on from generation {gen0}", flush=True)
    else:
        es = cma.CMAEvolutionStrategy([0.0] * len(planner.TUNABLE), 0.3,
                                      {"bounds": [-1, 1], "popsize": 12, "seed": 1, "verbose": -9})
        gen0, best, best_x = 0, None, None
        f_base = score(base, check, pool)
        print(f"current values on the check games: {f_base:.2f} hits/min", flush=True)
    for gen in range(gen0, generations):
        seeds = [1000 + gen * 10 + i for i in range(3)]  # new games every generation: no learning them by heart
        xs = es.ask()
        fs = [score(to_values(x, base), seeds, pool) for x in xs]
        es.tell(xs, fs)
        print(f"gen {gen}: best {min(fs):.2f} avg {sum(fs) / len(fs):.2f} hits/min", flush=True)
        if gen % 5 == 4 or gen == generations - 1:
            # the middle of the search is the best guess; check it on the same games as the hand-picked values
            f_mean = score(to_values(es.mean, base), check, pool)
            print(f"   current guess on the 18 check games: {f_mean:.2f} hits/min (current {f_base:.2f})",
                  flush=True)
            if f_mean < f_base and (best is None or f_mean < best):
                best, best_x = f_mean, list(es.mean)
                write_tuned(to_values(best_x, base), f"generation {gen + 1}, {best:.2f} hits/min on its check "
                                                     f"games vs {f_base:.2f} before")
        with open(STATE, "wb") as f:
            pickle.dump((es, gen + 1, best, best_x, f_base), f)
    if best_x is None:
        print("nothing beat the current values", flush=True)
    else:
        vals = to_values(best_x, base)
        for n in planner.TUNABLE:
            print(f"  {n:24s} {base[n]:>8.3g} -> {vals[n]:.3g}", flush=True)
    os.remove(STATE)
    pool.close()


def compare(seeds=range(9000, 9012)):
    pool = Pool(os.cpu_count())
    base = _base_values()
    import importlib
    import tuned
    importlib.reload(tuned)
    tuned_vals = dict(base, **{k: v for k, v in tuned.TUNED.items() if k in base})
    for name, vals in (("hand-picked", base), ("tuned", tuned_vals)):
        per = []
        for sc in SCENARIOS:
            res = pool.map(_job, [(vals, s, sc) for s in seeds])
            per.append(60.0 * sum(h for h, _ in res) / sum(t for _, t in res))
        print(f"{name:12s} " + "  ".join(f"{sc[0]}{sc[1]}: {p:.2f}" for sc, p in zip(SCENARIOS, per)) +
              f"   avg {sum(per) / len(per):.2f} hits/min", flush=True)
    pool.close()


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "check"
    if what == "tune":
        tune(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif what == "compare":
        compare()
    else:
        t = time.time()
        base = _base_values()
        for sc in SCENARIOS:
            print(sc, play(base, 1, sc), f"{time.time() - t:.1f}s", flush=True)
            t = time.time()
