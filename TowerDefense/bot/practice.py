"""
Practice: while the bot plays the real game, it also plays fast fake games in the background and keeps
tuning the planner's settings (planner.TUNABLE). Better settings are only taken when they beat the
current ones on the same test games, and the bot switches to them at its next new game.

Fast fake games: no pictures. The bot gets the true positions of everything (with a few pixels of noise,
like its eyes), decides 12 times a second like in the real game, and its keys arrive after the input
delay. Enemy and bullet speeds come from what it measured in the real game (learned.json). It plays hard
situations: an early and a late, crowded wave and a boss wave (enemies get more HP after every boss wave).
Score: hits per minute (lower is better).

It runs in its own processes at the lowest priority, on all CPU cores but one, so the real game and the
bot (which need to be quick) always go first.
"""

import json
import math
import os
import random
import time

import fakegame as fg
import planner
from tracker import Tracker
from vision import Thing

SCENARIOS = (("wave", 12), ("wave", 27), ("boss", 30))
SECONDS = 40.0
FPS = 12.0          # how often the real bot decides
DELAY = 0.12        # input delay (s)
NOISE = 3.0         # px of noise on every position (its eyes)
PHYS_DT = 1 / 60
RANGE = math.log(3.0)  # each setting may go from 1/3x to 3x of where the search started
CHECK_SEEDS = tuple(range(5000, 5006))
CONFIRM_SEEDS = tuple(range(6000, 6006))
BETTER = 0.95       # new settings must have at most this many hits as the current ones, on both test sets


# ---------------------------------------------------------------------------- the real game's numbers
def calibration(learned):
    """What the fake game should use, from learned.json (measured in the real game)."""
    cal = {"speed": {k: v for k, v in learned.get("speed", {}).items() if k in fg.SPEED}}
    me = learned.get("me", {}).get("speed")
    if me:
        cal["bullet_speed"] = {c: v / me for c, v in learned.get("bullet_speed", {}).items()
                               if c in fg.BULLET_SPEED and 0.2 < v / me < 3}
    return cal


_DEFAULT_SPEED, _DEFAULT_BULLET = dict(fg.SPEED), dict(fg.BULLET_SPEED)


def _calibrate(cal):
    fg.SPEED.clear()
    fg.SPEED.update(_DEFAULT_SPEED, **(cal or {}).get("speed", {}))
    fg.BULLET_SPEED.clear()
    fg.BULLET_SPEED.update(_DEFAULT_BULLET, **(cal or {}).get("bullet_speed", {}))


# ---------------------------------------------------------------------------- one fast game
def play(values, seed, scenario, cal=None):
    """One fast fake game with these planner settings. Returns (hits, seconds played)."""
    _calibrate(cal)
    for n, v in values.items():
        planner.set_setting(n, v)
    kind, wave = scenario
    g = fg.Game(seed, key_delay=DELAY, boss_wave=(kind == "boss"))
    g.mobs, g.pending = [], []
    g.wave = wave - 1
    g.next_wave()
    rnd = random.Random(seed * 7 + 1)
    pl, tr = planner.Planner(), Tracker()
    R = 1.5 * 19
    speeds = dict({c: v * fg.V for c, v in fg.BULLET_SPEED.items()}, **{"": 0.6 * fg.H})  # (as learned)
    next_decision, keys = 0.0, ()
    n = lambda: rnd.gauss(0, NOISE)  # noqa: E731
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


class Stopped(Exception):
    pass


def score(values, seeds, pool, cal=None, should_stop=None):
    """Hits per minute over every scenario x seed (every kind of game counts the same). Raises Stopped
    as soon as should_stop() says so (instead of waiting for all the games)."""
    jobs = [(values, s, sc, cal) for sc in SCENARIOS for s in seeds]
    if pool is None:
        res = [_job(j) for j in jobs]
    else:
        pending = pool.map_async(_job, jobs)
        while not pending.ready():
            pending.wait(0.2)
            if should_stop is not None and should_stop():
                raise Stopped
        res = pending.get()
    k = len(seeds)
    rates = [60.0 * sum(h for h, _ in res[i:i + k]) / sum(t for _, t in res[i:i + k]) for i in range(0, len(res), k)]
    return sum(rates) / len(rates)


def to_values(x, base):
    return {n: base[n] * math.exp(max(-1, min(1, xi)) * RANGE) for n, xi in zip(planner.TUNABLE, x)}


def current_values():
    return {n: planner.get_setting(n) for n in planner.TUNABLE}


# ---------------------------------------------------------------------------- the settings it found
def load_settings(path):
    """{name: value} from a practice result file (or {} if there's none)."""
    try:
        with open(path) as f:
            d = json.load(f)
        return {k: float(v) for k, v in d.get("values", {}).items() if k in planner.TUNABLE}
    except (OSError, ValueError, AttributeError):
        return {}


def apply_settings(values):
    for n, v in values.items():
        if n in planner.TUNABLE:
            planner.set_setting(n, v)


# ---------------------------------------------------------------------------- practicing in the background
def quiet_output():
    """In the exe there's no console: sys.stdout/stderr are None, and anything printing an error there
    (e.g. a practice process stopped mid-game) crashed with an error window. Send it nowhere instead."""
    import sys
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))


def _worker_init():
    quiet_output()
    _lowest_priority()


def _lowest_priority():
    """This process only gets the CPU nobody else wants (Windows: idle priority; elsewhere: nice 19)."""
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.SetPriorityClass(k32.GetCurrentProcess(), 0x40)  # IDLE_PRIORITY_CLASS
    except Exception:
        try:
            os.nice(19)
        except Exception:
            pass


def practice_main(start_values, learned_path, out_path, msgs, stop, workers=None):
    """Runs until `stop` is set: tunes the settings in fast fake games, writes better ones to out_path and
    reports progress through `msgs` (a multiprocessing queue of text lines)."""
    quiet_output()
    _lowest_priority()
    import cma
    from multiprocessing import Pool
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    pool = Pool(workers, initializer=_worker_init)
    say = lambda text: msgs.put(text)  # noqa: E731

    def learned_cal():
        try:
            with open(learned_path) as f:
                return calibration(json.load(f))
        except (OSError, ValueError):
            return {}

    cur = dict(start_values)
    games, gen, found = 0, 0, 0
    es = None
    t0 = time.time()
    from multiprocessing import parent_process
    parent = parent_process()
    halt = lambda: stop.is_set() or (parent is not None and not parent.is_alive())  # noqa: E731
    try:
        while not stop.is_set() and (parent is None or parent.is_alive()):  # (never outlives the app)
            if es is None:  # (re)start the search around the current settings
                es = cma.CMAEvolutionStrategy([0.0] * len(planner.TUNABLE), 0.3,
                                              {"bounds": [-1, 1], "popsize": 10, "verbose": -9})
                base = dict(cur)
            cal = learned_cal()
            seeds = [100000 + gen * 10 + i for i in range(2)]  # new games every round
            xs = es.ask()
            fs = []
            for x in xs:
                if halt():
                    return
                fs.append(score(to_values(x, base), seeds, pool, cal, halt))
            es.tell(xs, fs)
            games += len(xs) * len(seeds) * len(SCENARIOS)
            gen += 1
            if gen % 5 == 0:
                guess = to_values(es.mean, base)
                f_cur = score(cur, CHECK_SEEDS, pool, cal, halt)
                f_new = score(guess, CHECK_SEEDS, pool, cal, halt)
                note = f"{games} practice games, {(time.time() - t0) / 60:.0f} min"
                if f_new < BETTER * f_cur:
                    c_cur = score(cur, CONFIRM_SEEDS, pool, cal, halt)
                    c_new = score(guess, CONFIRM_SEEDS, pool, cal, halt)
                    if c_new < BETTER * c_cur:
                        found += 1
                        cur = guess
                        tmp = out_path + ".tmp"
                        with open(tmp, "w") as f:
                            json.dump({"values": cur, "hits_per_min": round((f_new + c_new) / 2, 3),
                                       "before": round((f_cur + c_cur) / 2, 3), "games": games,
                                       "time": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
                        os.replace(tmp, out_path)
                        es = None
                        say(f"Practice found better settings ({(f_cur + c_cur) / 2:.2f} -> "
                            f"{(f_new + c_new) / 2:.2f} hits/min in fake games); used from the next game. ({note})")
                        continue
                say(f"Practice: {note}, {found} improvements; current {f_cur:.2f} hits/min in fake games.")
    except Stopped:
        pass
    finally:
        pool.terminate()  # (its own worker processes: stopped here, not left behind)
        pool.join()


class Practice:
    """Starts/stops practice_main in its own process; read its news with poll()."""

    def __init__(self, learned_path, out_path):
        self.learned_path, self.out_path = learned_path, out_path
        self.proc = None

    def running(self):
        return self.proc is not None and self.proc.is_alive()

    def start(self):
        if self.running():
            return
        import multiprocessing as mp
        self.msgs, self.stop_ev = mp.Queue(), mp.Event()
        self.proc = mp.Process(target=practice_main, args=(current_values(), self.learned_path, self.out_path,
                                                            self.msgs, self.stop_ev))
        self.proc.start()

    def stop(self):
        """Asks it to stop; it ends its own games within a moment (killing it from outside would leave
        its worker processes behind)."""
        if self.proc is not None:
            self.stop_ev.set()
            self.proc.join(10)
            if self.proc.is_alive():
                self.proc.terminate()
            self.proc = None

    def poll(self):
        out = []
        if self.proc is None:
            return out
        try:
            while True:
                out.append(self.msgs.get_nowait())
        except Exception:
            pass
        return out
