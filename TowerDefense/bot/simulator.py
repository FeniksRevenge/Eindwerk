"""
Practice arena: watch the bot's real brain play a simulated version of the game, and let it
train itself to dodge better.

The world is simulated (no screen reading), but the bot's decisions come from exactly the same
Brain and Tracker it uses in Roblox, including its reaction delay.

- 10 HP; every hit costs 1. Killed mobs sometimes drop a green circle: walk over it for +2 HP.
- Purple tanks split into 3 tiny fast mobs when they die.
- It gets harder over time (an extra enemy every 15 s), like real waves.
- It keeps training while you watch: worker processes (at most half the CPU cores, low priority,
  so the game and the real bot come first) play test fights at full speed with small changes to the dodge settings and keep a change only if it survives longer.
  Better settings are used right away (also in the fight you're watching), saved, and used by the
  real bot too. When the player reaches 0/10 HP it simply plays again.

Open it from the app ("Simulator") or run:  py simulator.py
"""

import json
import math
import os
import random
import threading
import time
import tkinter as tk
from tkinter import ttk

from brain import Brain
from vision import Track, Tracker

W, H = 2534, 1239          # same size as the real play area in your screenshots
PR = 26.0                  # player radius
PSPEED = 700.0             # player speed (px/s), as measured in the real game
SIM_DT = 1 / 60
SPEEDS = (1, 2, 5, 10, 100)
BOT_DT = 1 / 14            # the real bot decides about 14x per second
LATENCY = 0.07             # screenshot -> keys delay
MAX_HP = 10
PICKUP_CHANCE = 0.05
RAMP_EVERY = 15.0          # seconds between extra enemies (not in a boss wave)
BOSS_SUMMON = 8.0          # the boss summons 3 grunts this often
SCENARIOS = {  # shooters, yellow, grunts, tanks, boss
    "Mixed": (3, 1, 3, 1, False),
    "Many shooters": (6, 3, 2, 0, False),
    "Boss": (0, 0, 0, 0, True),      # a boss wave is only the boss: it summons 3 grunts and shoots
    "Swarm (chasers)": (0, 0, 10, 2, False),
}
COLORS = {"grunt": "#e84a4a", "shooter": "#ffa040", "runner": "#f5d23c", "tank": "#b060f0",
          "tank_mini": "#d8a0ff", "boss": "#e84a4a", "health": "#5ee07a", "bullet_boss": "#e84a4a",
          "bullet_shooter": "#ffa040", "bullet_runner": "#f5d23c", "player": "#a8aab0"}
HP = {"grunt": 3, "shooter": 3, "runner": 4, "tank": 12, "tank_mini": 1, "boss": 150}
RADIUS = {"grunt": 43, "shooter": 35, "runner": 33, "tank": 70, "tank_mini": 32, "boss": 162}  # measured
SPEED = {"grunt": 140, "shooter": 150, "runner": 130, "tank": 80, "tank_mini": 210, "boss": 90}
RAMP_ORDER = ["shooter", "grunt", "runner", "tank", "shooter", "grunt"]

# Dodge settings the trainer may change: name -> (min, max). Defaults come from brain.Brain.
TRAIN_PARAMS = {
    "BULLET_MARGIN": (8, 60), "MOB_MARGIN": (20, 150), "BOSS_MARGIN": (0, 200),
    "CROWD_WEIGHT": (300, 9000), "EDGE_MARGIN": (40, 320), "EDGE_WEIGHT": (0.05, 3.0),
    "ORBIT_WEIGHT": (0, 600), "BOSS_AWAY": (0, 2), "BOSS_CENTER": (0, 5),
}
EPISODE_CAP = 240.0        # a training run ends after this many seconds even if still alive


class Obj:
    __slots__ = ("kind", "x", "y", "r", "vx", "vy", "hp", "cd", "cd2", "cd3", "rot", "src")

    def __init__(self, kind, x, y, r, vx=0.0, vy=0.0, hp=1, src=""):
        self.kind, self.x, self.y, self.r, self.vx, self.vy = kind, x, y, r, vx, vy
        self.hp, self.cd, self.cd2, self.cd3, self.rot, self.src = hp, 1.0, 1.0, 3.0, 0.0, src


class Sim:
    def __init__(self, scenario="Mixed", seed=None, brain_kw=None, oracle=False):
        self.rnd = random.Random(seed)
        self.scenario = scenario
        self.oracle = oracle  # testing: give the brain the true speeds instead of tracked ones
        self.px, self.py = W / 2, H / 2
        self.t, self.hits, self.kills, self.hp = 0.0, 0, 0, MAX_HP
        self.dead = False
        self.last_hit = -9.0
        self.next_bot, self.next_ramp, self.ramp_i = 0.0, RAMP_EVERY, 0
        self.keys, self.aim, self.fire = (), None, False
        self.pending = []
        self.shot_cd = 0.0
        self.objs, self.bullets, self.mine, self.pickups = [], [], [], []
        self.respawns = []  # (time, kind)
        self.tracker, self.brain = Tracker(), Brain(**(brain_kw or {}))
        self.corner_time = 0.0
        n_sh, n_ye, n_gr, n_tk, boss = SCENARIOS[scenario]
        for kind, n in (("shooter", n_sh), ("runner", n_ye), ("grunt", n_gr), ("tank", n_tk)):
            for _ in range(n):
                self.spawn(kind)
        if boss:
            self.spawn("boss")

    def spawn(self, kind, x=None, y=None):
        if x is None:
            side = self.rnd.randrange(4)
            x, y = ((self.rnd.uniform(0, W), 60) if side == 0 else (self.rnd.uniform(0, W), H - 60) if side == 1
                    else (60, self.rnd.uniform(0, H)) if side == 2 else (W - 60, self.rnd.uniform(0, H)))
        o = Obj(kind, x, y, RADIUS[kind], hp=HP[kind])
        o.cd, o.cd2, o.rot = self.rnd.uniform(0.5, 2), 1.0, self.rnd.uniform(0, 6)
        self.objs.append(o)

    # ------------------------------------------------------------------ the bot
    def bot_think(self):
        dets = {"player": [(self.px, self.py, PR)], "enemy_bullet": [], "grunt": [], "shooter": [],
                "runner": [], "tank": [], "boss": [], "tank_mini": [], "health": []}
        for o in self.objs:
            dets[o.kind].append((o.x, o.y, o.r))
        for b in self.bullets:
            dets["enemy_bullet"].append((b.x, b.y, b.r))
        for p in self.pickups:
            dets["health"].append((p.x, p.y, p.r))
        tracks = self.tracker.update(dets, BOT_DT, (self.px, self.py), 1200 * PR / 13, 260 * PR / 13)
        if self.oracle:
            tracks = []
            for o in self.objs + self.bullets + self.pickups:
                t = Track(o.x, o.y, o.r, "enemy_bullet" if o.kind == "bullet" else o.kind, o.vx, o.vy)
                t.age = 10
                tracks.append(t)
        keys, aim, fire = self.brain.think((self.px, self.py, PR), PSPEED, tracks, W, H, latency=LATENCY)
        self.pending.append((self.t + LATENCY, keys, aim, fire))

    def kill(self, o):
        self.objs.remove(o)
        self.kills += 1
        if o.kind == "tank":  # splits into 3 tiny ones
            for i in range(3):
                a = i * 2 * math.pi / 3
                self.spawn("tank_mini", o.x + math.cos(a) * 40, o.y + math.sin(a) * 40)
        if o.kind != "tank_mini" and (self.scenario != "Boss" or o.kind == "boss"):  # boss wave: only the boss summons
            self.respawns.append((self.t + (10.0 if o.kind == "boss" else 2.5), o.kind))
        if self.rnd.random() < PICKUP_CHANCE:
            self.pickups.append(Obj("health", o.x, o.y, 18))

    # ------------------------------------------------------------------ one tick
    def step(self, dt=SIM_DT):
        if self.dead:
            return
        if self.t >= self.next_bot:
            self.next_bot = self.t + BOT_DT
            self.bot_think()
        while self.pending and self.pending[0][0] <= self.t:
            _, self.keys, self.aim, self.fire = self.pending.pop(0)
        dx = ("d" in self.keys) - ("a" in self.keys)
        dy = ("s" in self.keys) - ("w" in self.keys)
        n = math.hypot(dx, dy) or 1
        self.px = min(max(self.px + dx / n * PSPEED * dt, PR), W - PR)
        self.py = min(max(self.py + dy / n * PSPEED * dt, PR), H - PR)

        # the player's own gun
        self.shot_cd -= dt
        if self.fire and self.aim and self.shot_cd <= 0:
            self.shot_cd = 0.12
            d = math.hypot(self.aim[0] - self.px, self.aim[1] - self.py) or 1
            self.mine.append(Obj("mine", self.px, self.py, 7, (self.aim[0] - self.px) / d * 1640,
                                 (self.aim[1] - self.py) / d * 1640))

        # harder over time
        if self.t >= self.next_ramp and self.scenario != "Boss":
            self.next_ramp += RAMP_EVERY
            self.spawn(RAMP_ORDER[self.ramp_i % len(RAMP_ORDER)])
            self.ramp_i += 1

        px, py = self.px, self.py
        for o in self.objs:
            d = math.hypot(px - o.x, py - o.y) or 1
            nx, ny = (px - o.x) / d, (py - o.y) / d
            sp = SPEED[o.kind]
            if o.kind in ("grunt", "tank", "tank_mini", "boss"):
                o.x += nx * sp * dt
                o.y += ny * sp * dt
            else:  # shooters keep their distance and circle
                rad = 1 if d > 700 else -1 if d < 500 else 0
                o.x = min(max(o.x + (nx * rad - ny * 0.6) * sp * dt, 40), W - 40)
                o.y = min(max(o.y + (ny * rad + nx * 0.6) * sp * dt, 40), H - 40)
            o.cd -= dt
            o.cd2 -= dt
            if o.kind == "shooter" and o.cd <= 0:
                o.cd = 1.4
                self.bullets.append(Obj("bullet", o.x, o.y, 14, nx * 650, ny * 650, src="shooter"))
            elif o.kind == "runner" and o.cd <= 0:
                o.cd, o.rot = 2.0, o.rot + 0.3
                for i in range(8):
                    a = o.rot + i * math.pi / 4
                    self.bullets.append(Obj("bullet", o.x, o.y, 13, math.cos(a) * 450, math.sin(a) * 450, src="runner"))
            elif o.kind == "boss":
                o.cd3 -= dt
                if o.cd3 <= 0:  # summons 3 grunts next to itself
                    o.cd3 = BOSS_SUMMON
                    for i in range(3):
                        a = self.rnd.uniform(0, 2 * math.pi)
                        self.spawn("grunt", min(max(o.x + math.cos(a) * (o.r + 60), 40), W - 40),
                                   min(max(o.y + math.sin(a) * (o.r + 60), 40), H - 40))
                if o.cd <= 0:
                    o.cd, o.rot = 2.6, o.rot + 0.17
                    for i in range(18):
                        a = o.rot + i * 2 * math.pi / 18
                        self.bullets.append(Obj("bullet", o.x, o.y, 15, math.cos(a) * 380, math.sin(a) * 380, src="boss"))
                if o.cd2 <= 0:
                    o.cd2 = 1.6
                    a0 = math.atan2(ny, nx)
                    for off in (-0.2, 0, 0.2):
                        self.bullets.append(Obj("bullet", o.x, o.y, 15, math.cos(a0 + off) * 550,
                                                math.sin(a0 + off) * 550, src="boss"))
        for b in self.bullets + self.mine:
            b.x += b.vx * dt
            b.y += b.vy * dt
        inside = lambda b: -60 < b.x < W + 60 and -60 < b.y < H + 60
        self.bullets = [b for b in self.bullets if inside(b)]
        # player bullets hit mobs
        keep = []
        for b in self.mine:
            hit = next((o for o in self.objs if math.hypot(o.x - b.x, o.y - b.y) < o.r + b.r), None)
            if hit is None:
                if inside(b):
                    keep.append(b)
                continue
            hit.hp -= 1
            if hit.hp <= 0:
                self.kill(hit)
        self.mine = keep
        for when, kind in [r for r in self.respawns if r[0] <= self.t]:
            self.respawns.remove((when, kind))
            self.spawn(kind)
        # health pickups: +2 HP
        for p in list(self.pickups):
            if math.hypot(p.x - px, p.y - py) < p.r + PR:
                self.pickups.remove(p)
                self.hp = min(MAX_HP, self.hp + 2)
        # getting hit (0.5 s of invulnerability after a hit, like a blink)
        if self.t - self.last_hit > 0.5:
            for o in self.objs + self.bullets:
                if math.hypot(o.x - px, o.y - py) < o.r + PR:
                    self.hits += 1
                    self.hp -= 1
                    self.last_hit = self.t
                    if self.hp <= 0:
                        self.dead = True
                    break
        if min(px, W - px) < 250 and min(py, H - py) < 250:
            self.corner_time += dt
        self.t += dt


def run_episode(scenario, seed, params, cap=EPISODE_CAP, on_sim=None, stop=None):
    """Plays one fight until death or `cap` seconds. Returns a score (higher = better)."""
    sim = Sim(scenario, seed=seed, brain_kw=params)
    if on_sim:
        on_sim(sim)
    while not sim.dead and sim.t < cap:
        if stop is not None and stop.is_set():
            break
        sim.step()
    # survival time first; with equal survival, more HP left and fewer hits win
    return sim.t + 2.0 * max(sim.hp, 0) - 0.5 * sim.hits


def benchmark(scenario, seeds=range(6), seconds=60, oracle=False, **brain_kw):
    """Average hits per minute and corner seconds per minute for a brain setting (no window).
    HP doesn't end these runs."""
    hits = corner = 0.0
    for seed in seeds:
        sim = Sim(scenario, seed=seed, brain_kw=brain_kw, oracle=oracle)
        while sim.t < seconds:
            sim.dead = False
            sim.hp = MAX_HP
            sim.step()
        hits += sim.hits
        corner += sim.corner_time
    n = len(seeds) * seconds / 60
    return hits / n, corner / n


def default_params():
    return {k: float(getattr(Brain, k)) for k in TRAIN_PARAMS}


def mutate(params, rnd):
    new = dict(params)
    for name in rnd.sample(list(TRAIN_PARAMS), rnd.choice([1, 2, 3])):
        lo, hi = TRAIN_PARAMS[name]
        v = new[name] if new[name] > 0 else (hi - lo) * 0.05
        new[name] = round(min(hi, max(lo, v * math.exp(rnd.gauss(0, 0.3)))), 3)
    return new


def _episode(job):
    """One training fight, run in a worker process: (scenario, seed, params) -> score."""
    scenario, seed, params = job
    return run_episode(scenario, seed, params)


def selftest_worker(x):
    """Used by the exe's self-test to check training worker processes start."""
    return run_episode("Mixed", x, default_params(), cap=2.0) > 0


def _low_priority():
    """Training workers run at low priority, so the game and the real bot always come first."""
    try:
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(10)
    except Exception:
        pass


def make_pool():
    """Worker processes for training in parallel with the fight you watch: at most half the CPU
    cores (max 4), at low priority. Returns (pool or None, number of workers)."""
    workers = max(1, min(4, (os.cpu_count() or 2) // 2))
    try:
        import multiprocessing as mp
        return mp.get_context("spawn").Pool(workers, initializer=_low_priority), workers
    except Exception:
        return None, 1


class Trainer:
    """Hill climbing on the dodge settings. Each round: pick a few fights (fixed seeds so every
    candidate faces the same bullets), play them with the current best and with several random
    changes of it (all at once, on the worker processes), and keep the best change if it beats the
    current settings by more than 3%."""

    def __init__(self, params, scenario, on_status=None, pool=None, workers=1, candidates=None, seeds_per=4):
        self.best = dict(params)
        self.scenario = scenario
        self.on_status = on_status or (lambda s: None)
        self.pool, self.workers = pool, workers
        # more cores = more changes tried per round, in about the same time
        self.candidates = candidates or max(6, 2 * workers)
        self.seeds_per = seeds_per
        self.rnd = random.Random()
        self.stop = threading.Event()
        self.rounds = 0
        self.improved = 0
        self.best_score = None

    def _run_all(self, jobs):
        if self.pool is not None:
            res = self.pool.map_async(_episode, jobs)
            while not res.ready():
                if self.stop.is_set():
                    return None
                res.wait(0.2)
            return res.get()
        out = []
        for job in jobs:
            if self.stop.is_set():
                return None
            out.append(run_episode(*job, stop=self.stop))
        return out

    def round(self):
        """One round. Returns True if it found better settings (now in self.best)."""
        self.rounds += 1
        seeds = [self.rnd.randrange(1_000_000) for _ in range(self.seeds_per)]
        cands = [self.best] + [mutate(self.best, self.rnd) for _ in range(self.candidates)]
        self.on_status(f"round {self.rounds}: trying {self.candidates} changes on {len(seeds)} fights "
                       f"({self.workers} core{'s' if self.workers > 1 else ''})")
        results = self._run_all([(self.scenario, s, c) for c in cands for s in seeds])
        if results is None:
            return False
        n = len(seeds)
        scores = [sum(results[i * n:(i + 1) * n]) / n for i in range(len(cands))]
        base = scores[0]
        best_i = max(range(1, len(cands)), key=lambda i: scores[i])
        if scores[best_i] > base * 1.03:
            self.best, self.best_score = cands[best_i], scores[best_i]
            self.improved += 1
            return True
        self.best_score = base
        return False


class SimWindow:
    SCALE = 0.5

    def __init__(self, master=None, load_params=None, save_params=None):
        self.load_params = load_params or _load_params_file
        self.save_params = save_params or _save_params_file
        self.params = {**default_params(), **(self.load_params() or {})}
        self.root = tk.Toplevel(master) if master else tk.Tk()
        self.root.title("Swarm Bot - practice arena")
        self.root.configure(bg="#07090d")
        bar = tk.Frame(self.root, bg="#07090d", padx=10, pady=8)
        bar.pack(fill="x")
        self.speed = 1
        self.paused = False
        self.speed_btns = {}
        for sp in SPEEDS:
            b = ttk.Button(bar, text=f"{sp}x", width=5, command=lambda sp=sp: self.set_speed(sp))
            b.pack(side="left", padx=(0, 4))
            self.speed_btns[sp] = b
        self.pause_btn = ttk.Button(bar, text="Pause", command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=(8, 4))
        ttk.Button(bar, text="Restart", command=self.restart).pack(side="left", padx=(0, 8))
        self.scen = tk.StringVar(value="Mixed")
        box = ttk.Combobox(bar, textvariable=self.scen, values=list(SCENARIOS), state="readonly", width=15)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _e: self.scenario_changed())
        self.train_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Keep training while it plays", variable=self.train_on,
                        command=self.train_toggled).pack(side="left", padx=(10, 4))
        ttk.Button(bar, text="Reset training", command=self.reset_training).pack(side="left", padx=(4, 0))
        self.info = tk.StringVar()
        tk.Label(self.root, textvariable=self.info, bg="#07090d", fg="#e4e7ec", font=("Consolas", 10),
                 anchor="w", justify="left").pack(fill="x", padx=10)
        self.canvas = tk.Canvas(self.root, width=int(W * self.SCALE), height=int(H * self.SCALE),
                                bg="#05070b", highlightthickness=0)
        self.canvas.pack(padx=10, pady=(4, 10))
        self.pool, self.workers = None, 1
        self.trainer = None
        self.train_status = "starting..."
        self.train_result = ""
        self.message = ""
        self.best_run = 0.0
        self.died_at = None
        self.closed = False
        self.restart()
        self.set_speed(1)
        self.last = time.perf_counter()
        self.last_draw = 0.0
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(16, self.loop)
        self.train_toggled()

    # ------------------------------------------------------------------ controls
    def set_speed(self, sp):
        self.speed = sp
        for s, b in self.speed_btns.items():
            b.state(["pressed"] if s == sp else ["!pressed"])
        self.real_start, self.sim_start = time.perf_counter(), self.sim.t

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.config(text="Resume" if self.paused else "Pause")
        self.real_start, self.sim_start = time.perf_counter(), self.sim.t

    def restart(self):
        self.sim = Sim(self.scen.get(), brain_kw=self.params)
        self.died_at = None
        self.real_start, self.sim_start = time.perf_counter(), 0.0

    def scenario_changed(self):
        self.restart()
        if self.trainer:  # train on the fights you're watching
            self.stop_training()
            self.train_toggled()

    def reset_training(self):
        self.stop_training()
        self.params = default_params()
        self.save_params(None)
        self.train_result = ""
        self.message = "Training reset to the default settings."
        self.restart()
        self.train_toggled()

    # ------------------------------------------------------------------ background training
    def train_toggled(self):
        if self.train_on.get() and self.trainer is None and not self.closed:
            self.start_training()
        elif not self.train_on.get():
            self.stop_training()
            self.train_status = "off"

    def stop_training(self):
        if self.trainer:
            self.trainer.stop.set()
            self.trainer = None

    def start_training(self):
        tr = Trainer(self.params, self.scen.get(), on_status=self._set_status)
        self.trainer = tr

        def work():
            if self.pool is None:
                self._set_status("starting the training workers...")
                self.pool, self.workers = make_pool()
            tr.pool, tr.workers = self.pool, self.workers
            tr.candidates = max(6, 2 * self.workers)
            while not tr.stop.is_set():
                better = tr.round()
                if tr.stop.is_set():
                    break
                if better:
                    self.params = dict(tr.best)
                    self.save_params(self.params)
                    # the fight you're watching switches to the better settings right away
                    for name, value in self.params.items():
                        setattr(self.sim.brain, name, float(value))
                    self.train_result = (f"round {tr.rounds} found better settings (~{tr.best_score:.0f}s per test fight), "
                                         f"saved and used right away (also by the real bot). Improvements: {tr.improved}")
                else:
                    self.train_result = (f"round {tr.rounds}: no change beat the current settings "
                                         f"(~{tr.best_score:.0f}s per test fight). Improvements: {tr.improved}")

        threading.Thread(target=work, daemon=True).start()

    def _set_status(self, text):
        self.train_status = text

    def close(self):
        self.closed = True
        self.stop_training()
        if self.pool is not None:
            try:
                self.pool.terminate()
            except Exception:
                pass
        self.root.destroy()

    # ------------------------------------------------------------------ loop
    def loop(self):
        if self.closed:
            return
        now = time.perf_counter()
        frame_dt = min(0.1, now - self.last)
        self.last = now
        if self.sim.dead:
            # Died: show it for a moment, then play again (with the newest trained settings).
            if self.died_at is None:
                self.died_at = now
                self.best_run = max(self.best_run, self.sim.t)
                self.message = f"Died after {self.sim.t:.0f}s (best {self.best_run:.0f}s). Playing again..."
            elif now - self.died_at > 1.5:
                self.restart()
        elif not self.paused:
            todo = frame_dt * self.speed
            # At high speed spend most of the time simulating (it still can't freeze the window).
            deadline = now + (0.08 if self.speed >= 10 else 0.04)
            while todo > 1e-9 and time.perf_counter() < deadline and not self.sim.dead:
                step = min(SIM_DT, todo)
                self.sim.step(step)
                todo -= step
        # Redraw at most 30x a second (10x at fast speeds): drawing costs more than playing.
        if now - self.last_draw >= (0.1 if self.speed >= 10 else 1 / 30):
            self.last_draw = now
            try:
                self.draw()
            except (RuntimeError, ValueError):
                pass
        self.root.after(4 if self.speed >= 10 else 16, self.loop)

    def draw(self):
        c, s, sim = self.canvas, self.SCALE, self.sim
        c.delete("all")
        for p in list(sim.pickups):
            r = p.r * s
            c.create_oval(p.x * s - r, p.y * s - r, p.x * s + r, p.y * s + r, outline=COLORS["health"], width=2)
            c.create_rectangle(p.x * s - r / 2, p.y * s - r / 2, p.x * s + r / 2, p.y * s + r / 2, fill=COLORS["health"], outline="")
        for o in list(sim.objs):
            x, y, r = o.x * s, o.y * s, o.r * s
            col = COLORS[o.kind]
            if o.kind in ("grunt", "tank", "tank_mini"):
                hollow = o.kind == "tank"
                c.create_rectangle(x - r * 0.75, y - r * 0.75, x + r * 0.75, y + r * 0.75, outline=col,
                                   width=3 if hollow else 0, fill="" if hollow else col)
            elif o.kind in ("shooter", "runner"):
                c.create_oval(x - r, y - r, x + r, y + r, outline=col)
                c.create_oval(x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4, fill=col, outline="")
            else:  # boss
                c.create_rectangle(x - r * 0.35, y - r, x + r * 0.35, y + r, fill=col, outline="")
                c.create_rectangle(x - r, y - r * 0.35, x + r, y + r * 0.35, fill=col, outline="")
        for b in list(sim.bullets):
            x, y, r = b.x * s, b.y * s, b.r * s
            c.create_oval(x - r, y - r, x + r, y + r, fill=COLORS["bullet_" + b.src], outline="")
        for b in list(sim.mine):
            c.create_oval(b.x * s - 2, b.y * s - 2, b.x * s + 2, b.y * s + 2, fill="#ffffff", outline="")
        px, py, pr = sim.px * s, sim.py * s, PR * s
        if sim.aim:
            c.create_line(px, py, sim.aim[0] * s, sim.aim[1] * s, fill="#5a1a1a")
        flash = sim.t - sim.last_hit < 0.5
        c.create_oval(px - pr, py - pr, px + pr, py + pr, fill="#ff5050" if flash else COLORS["player"], outline="#ffffff")
        dx = ("d" in sim.keys) - ("a" in sim.keys)
        dy = ("s" in sim.keys) - ("w" in sim.keys)
        if dx or dy:
            n = math.hypot(dx, dy)
            c.create_line(px, py, px + dx / n * 30, py + dy / n * 30, fill="#6fdc8c", width=3, arrow="last")
        # HP bar (top left, like the game)
        c.create_rectangle(10, 10, 210, 34, fill="#2a0f10", outline="#5a2a2a")
        c.create_rectangle(10, 10, 10 + 200 * max(sim.hp, 0) / MAX_HP, 34, fill="#c0303a", outline="")
        c.create_text(110, 22, text=f"{max(sim.hp, 0)} / {MAX_HP}", fill="#ffffff", font=("Consolas", 11, "bold"))
        if sim.dead:
            c.create_text(W * s / 2, H * s / 2, text="DIED", fill="#ff5050", font=("Consolas", 36, "bold"))
        minutes = max(sim.t, 1e-6) / 60
        real = max(1e-6, time.perf_counter() - self.real_start)
        actual = (sim.t - self.sim_start) / real
        line = (f"time {sim.t:5.0f}s   HP {max(sim.hp, 0)}/{MAX_HP}   hits {sim.hits} ({sim.hits / minutes:.1f}/min)   "
                f"kills {sim.kills}   keys {''.join(sim.keys).upper() or '-':2}   running at {actual:.0f}x"
                + ("   (as fast as this PC can)" if actual < self.speed * 0.8 else ""))
        line += f"\nTraining in the background: {self.train_status}"
        if self.train_result:
            line += f"\nLast training: {self.train_result}"
        self.info.set(line + (f"\n{self.message}" if self.message else ""))


_PARAMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_params.json")


def _load_params_file():
    try:
        with open(_PARAMS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_params_file(params):
    try:
        if params is None:
            os.remove(_PARAMS_FILE)
        else:
            with open(_PARAMS_FILE, "w") as f:
                json.dump(params, f, indent=2)
    except OSError:
        pass


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    SimWindow()
    tk.mainloop()
