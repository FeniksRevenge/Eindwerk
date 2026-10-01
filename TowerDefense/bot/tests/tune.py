"""
Tunes all of the planner's settings (planner.TUNABLE) by playing thousands of fake games, and writes the
best ones to tuned.py (which the planner loads). Not part of the app.

Fast mode: no pictures. The bot gets the true positions of everything (with a few pixels of noise, like
its eyes), decides 12 times a second like it does in the real game, and its keys arrive after the input
delay. It plays hard situations: late waves (lots of enemies at once) and the boss wave. Score: hits per
minute (lower is better).

    python tests/tune.py check                 # play the current settings once, see the speed
    python tests/tune.py tune [generations]    # tune (uses every CPU core), writes tuned.py
    python tests/tune.py compare               # tuned.py vs the hand-picked values, on games it never saw

Needs: pip install cma
"""

import math
import os
import random
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)
sys.path.insert(0, HERE)

import fakegame as fg  # noqa: E402
import planner  # noqa: E402
from tracker import Tracker  # noqa: E402
from vision import Thing  # noqa: E402

SCENARIOS = (("wave", 12), ("wave", 20), ("boss", 1))
SECONDS = 40.0
FPS = 12.0          # how often the real bot decides
DELAY = 0.12        # input delay (s)
NOISE = 3.0         # px of noise on every position (its eyes)
PHYS_DT = 1 / 60
RANGE = math.log(3.0)  # each setting may go from 1/3x to 3x its hand-picked value


def _base_values():
    """The hand-picked values (planner.py itself, without tuned.py)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("planner_plain", os.path.join(BOT, "planner.py"))
    src = open(os.path.join(BOT, "planner.py")).read().replace("from tuned import TUNED", "raise ImportError")
    mod = importlib.util.module_from_spec(spec)
    exec(compile(src, "planner_plain", "exec"), mod.__dict__)
    return {n: mod.get_setting(n) for n in mod.TUNABLE}


def play(values, seed, scenario):
    """One fast fake game with these settings. Returns (hits, seconds played)."""
    for n, v in values.items():
        planner.set_setting(n, v)
    kind, wave = scenario
    g = fg.Game(seed, key_delay=DELAY, boss_wave=(kind == "boss"))
    if kind == "wave":
        g.wave = wave - 1
        g.next_wave()
    rnd = random.Random(seed * 7 + 1)
    pl, tr = planner.Planner(), Tracker()
    R = 1.5 * 19
    speeds = dict({c: v * fg.V for c, v in fg.BULLET_SPEED.items()}, **{"": 0.6 * fg.H})  # (as learned)
    next_decision, keys = 0.0, ()
    n = lambda: rnd.gauss(0, NOISE)
    while g.t < SECONDS and not g.dead:
        if g.t >= next_decision:
            dt = 1 / FPS
            next_decision += dt
            things = [Thing(o.kind, o.x + n(), o.y + n(), o.r * 1.1) for o in g.mobs]
            things += [Thing("bullet", b.x + n(), b.y + n(), b.r, b.src) for b in g.bullets]
            things += [Thing("health", p.x, p.y, p.r) for p in g.pickups]
            px, py = g.px + n(), g.py + n()
            tracks = tr.update(things, dt, (px, py), 1.6 * fg.H, speeds)
            # where you'll be when new keys land: the keys already sent keep moving you meanwhile
            sx, sy = px, py
            pending = [(t, v) for t, k, v in g.queue if k == "keys"]
            cur, t0 = g.keys, g.t
            for t1, nxt in pending + [(g.t + DELAY, None)]:
                dx = ("right" in cur) - ("left" in cur)
                dy = ("down" in cur) - ("up" in cur)
                m = math.hypot(dx, dy) or 1
                sx += dx / m * fg.V * (t1 - t0)
                sy += dy / m * fg.V * (t1 - t0)
                cur, t0 = nxt, t1
            new, aim = pl.plan((px, py, R), fg.V, tracks, fg.W, fg.H, latency=DELAY + 0.5 / FPS, start=(sx, sy))
            if new != keys:
                g.queue.append((g.t + DELAY, "keys", new))
                keys = new
            g.aim = aim if aim is not None else g.aim
            g.firing = True
        g.step(PHYS_DT)
    return g.hits, g.t


def _job(args):
    return play(*args)


def score(values, seeds, pool):
    jobs = [(values, s, sc) for sc in SCENARIOS for s in seeds]
    res = pool.map(_job, jobs) if pool else [_job(j) for j in jobs]
    k = len(seeds)
    rates = [60.0 * sum(h for h, _ in res[i:i + k]) / sum(t for _, t in res[i:i + k]) for i in range(0, len(res), k)]
    return sum(rates) / len(rates)  # every kind of game counts the same


def to_values(x, base):
    return {n: base[n] * math.exp(max(-1, min(1, xi)) * RANGE) for n, xi in zip(planner.TUNABLE, x)}


def write_tuned(values, note):
    lines = ['"""Planner settings tuned by tests/tune.py (fake game, %s). Delete this file to use the',
             'hand-picked values in planner.py."""', "", "TUNED = {"]
    lines[0] = lines[0] % note
    for n in planner.TUNABLE:
        lines.append(f"    {n!r}: {values[n]:.4g},")
    lines.append("}")
    with open(os.path.join(BOT, "tuned.py"), "w") as f:
        f.write("\n".join(lines) + "\n")


def tune(generations=30):
    import cma
    base = _base_values()
    pool = Pool(os.cpu_count())
    es = cma.CMAEvolutionStrategy([0.0] * len(planner.TUNABLE), 0.3,
                                  {"bounds": [-1, 1], "popsize": 12, "seed": 1, "verbose": -9})
    best, best_x = None, None
    for gen in range(generations):
        seeds = [1000 + gen * 10 + i for i in range(3)]  # new games every generation: no learning them by heart
        xs = es.ask()
        fs = [score(to_values(x, base), seeds, pool) for x in xs]
        es.tell(xs, fs)
        m = es.mean
        print(f"gen {gen}: best {min(fs):.2f} avg {sum(fs) / len(fs):.2f} hits/min", flush=True)
        if gen % 5 == 4 or gen == generations - 1:
            # the middle of the search is the best guess; check it against the hand-picked values
            check = [5000 + i for i in range(6)]
            f_mean = score(to_values(m, base), check, pool)
            print(f"   current guess on 18 new games: {f_mean:.2f} hits/min", flush=True)
            if best is None or f_mean < best:
                best, best_x = f_mean, list(m)
    vals = to_values(best_x, base)
    write_tuned(vals, f"{generations} generations, {best:.2f} hits/min on its check games")
    for n in planner.TUNABLE:
        print(f"  {n:24s} {base[n]:>8.3g} -> {vals[n]:.3g}")
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
