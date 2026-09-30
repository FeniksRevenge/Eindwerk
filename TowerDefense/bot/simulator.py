"""
Practice arena: watch the bot's real brain play a simulated version of the game, and let it
train itself to dodge better.

The world is simulated (no screen reading), but the bot's decisions come from exactly the same
Brain and Tracker it uses in Roblox, including its reaction delay.

- 10 HP; every hit costs 1. Killed mobs sometimes drop a green circle: walk over it for +2 HP.
- Purple tanks split into 3 tiny fast mobs when they die.
- It gets harder over time (an extra enemy every 15 s), like real waves.
- When the player reaches 0/10 HP the run stops and (with auto-train on) it trains: it tries small
  changes to its dodge settings, replays the same fights with each at full speed, and keeps a change
  only if it survives longer. The best settings are saved and also used by the real bot.

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
BOT_DT = 1 / 14            # the real bot decides about 14x per second
LATENCY = 0.07             # screenshot -> keys delay
MAX_HP = 10
PICKUP_CHANCE = 0.05
RAMP_EVERY = 15.0          # seconds between extra enemies
SCENARIOS = {  # shooters, yellow, grunts, tanks, boss
    "Mixed": (3, 1, 3, 1, True),
    "Many shooters": (6, 3, 2, 0, False),
    "Boss": (2, 1, 2, 0, True),
    "Swarm (chasers)": (0, 0, 10, 2, False),
}
COLORS = {"grunt": "#e84a4a", "shooter": "#ffa040", "runner": "#f5d23c", "tank": "#b060f0",
          "tank_mini": "#d8a0ff", "boss": "#e84a4a", "health": "#5ee07a", "bullet_boss": "#e84a4a",
          "bullet_shooter": "#ffa040", "bullet_runner": "#f5d23c", "player": "#a8aab0"}
HP = {"grunt": 3, "shooter": 3, "runner": 4, "tank": 12, "tank_mini": 1, "boss": 150}
RADIUS = {"grunt": 43, "shooter": 38, "runner": 33, "tank": 63, "tank_mini": 22, "boss": 128}
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
    __slots__ = ("kind", "x", "y", "r", "vx", "vy", "hp", "cd", "cd2", "rot", "src")

    def __init__(self, kind, x, y, r, vx=0.0, vy=0.0, hp=1, src=""):
        self.kind, self.x, self.y, self.r, self.vx, self.vy = kind, x, y, r, vx, vy
        self.hp, self.cd, self.cd2, self.rot, self.src = hp, 1.0, 1.0, 0.0, src


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
        if o.kind != "tank_mini":
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
        if self.t >= self.next_ramp:
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


class Trainer:
    """Hill climbing on the dodge settings. Each round: pick 3 fights (fixed seeds so every candidate
    faces the same bullets), score the current best on them, then try `candidates` mutations and keep
    any that beat it. Runs on a background thread."""

    def __init__(self, params, scenario, on_sim=None, on_status=None, candidates=6, seeds_per=3):
        self.best = dict(params)
        self.scenario = scenario
        self.on_sim, self.on_status = on_sim, on_status or (lambda s: None)
        self.candidates, self.seeds_per = candidates, seeds_per
        self.rnd = random.Random()
        self.stop = threading.Event()
        self.improved = 0
        self.best_score = None

    def score(self, params, seeds, label):
        total = 0.0
        for i, seed in enumerate(seeds, 1):
            self.on_status(f"{label}: fight {i}/{len(seeds)}")
            total += run_episode(self.scenario, seed, params, on_sim=self.on_sim, stop=self.stop)
            if self.stop.is_set():
                return None
        return total / len(seeds)

    def round(self):
        seeds = [self.rnd.randrange(1_000_000) for _ in range(self.seeds_per)]
        base = self.score(self.best, seeds, "Measuring current settings")
        if base is None:
            return
        self.best_score = base
        for c in range(1, self.candidates + 1):
            cand = mutate(self.best, self.rnd)
            s = self.score(cand, seeds, f"Trying change {c}/{self.candidates} (best {base:.0f}s)")
            if s is None:
                return
            if s > base * 1.03:
                self.best, base = cand, s
                self.best_score = s
                self.improved += 1


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
        for sp in (1, 2, 5, 10):
            b = ttk.Button(bar, text=f"{sp}x", width=4, command=lambda sp=sp: self.set_speed(sp))
            b.pack(side="left", padx=(0, 4))
            self.speed_btns[sp] = b
        self.pause_btn = ttk.Button(bar, text="Pause", command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=(8, 4))
        ttk.Button(bar, text="Restart", command=self.restart).pack(side="left", padx=(0, 8))
        self.scen = tk.StringVar(value="Mixed")
        box = ttk.Combobox(bar, textvariable=self.scen, values=list(SCENARIOS), state="readonly", width=15)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _e: self.restart())
        self.auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Auto-train when it dies", variable=self.auto).pack(side="left", padx=(10, 4))
        self.train_btn = ttk.Button(bar, text="Train now", command=self.start_training)
        self.train_btn.pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Reset training", command=self.reset_training).pack(side="left", padx=(4, 0))
        self.info = tk.StringVar()
        tk.Label(self.root, textvariable=self.info, bg="#07090d", fg="#e4e7ec", font=("Consolas", 10),
                 anchor="w", justify="left").pack(fill="x", padx=10)
        self.canvas = tk.Canvas(self.root, width=int(W * self.SCALE), height=int(H * self.SCALE),
                                bg="#05070b", highlightthickness=0)
        self.canvas.pack(padx=10, pady=(4, 10))
        self.trainer = None
        self.train_status = ""
        self.message = ""
        self.restart()
        self.set_speed(1)
        self.last = time.perf_counter()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(16, self.loop)

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
        self.real_start, self.sim_start = time.perf_counter(), 0.0

    def reset_training(self):
        if self.trainer:
            self.trainer.stop.set()
        self.params = default_params()
        self.save_params(None)
        self.message = "Training reset to the default settings."
        self.restart()

    def start_training(self):
        if self.trainer:
            return
        self.message = ""
        scen = self.scen.get()

        def on_sim(sim):
            self.sim = sim  # show the fight being trained on

        def on_status(text):
            self.train_status = text

        self.trainer = Trainer(self.params, scen, on_sim=on_sim, on_status=on_status)

        def work():
            tr = self.trainer
            tr.round()
            if not tr.stop.is_set():
                if tr.improved:
                    self.params = tr.best
                    self.save_params(self.params)
                    self.message = (f"Training found {tr.improved} better setting(s): survives ~{tr.best_score:.0f}s "
                                    "per fight now. Saved; the real bot uses them too.")
                else:
                    self.message = f"Training round done: no change beat the current settings (~{tr.best_score:.0f}s)."
            self.trainer = None
            try:
                self.root.after(0, self.restart)
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=work, daemon=True).start()

    def close(self):
        if self.trainer:
            self.trainer.stop.set()
        self.root.destroy()

    # ------------------------------------------------------------------ loop
    def loop(self):
        now = time.perf_counter()
        frame_dt = min(0.1, now - self.last)
        self.last = now
        if not self.paused and self.trainer is None:
            todo = frame_dt * self.speed
            deadline = now + 0.05  # don't freeze the window if the PC can't keep up
            while todo > 1e-9 and time.perf_counter() < deadline and not self.sim.dead:
                step = min(SIM_DT, todo)
                self.sim.step(step)
                todo -= step
            if self.sim.dead and self.auto.get():
                self.message = f"Died after {self.sim.t:.0f}s. Training a better way to dodge..."
                self.start_training()
        try:
            self.draw()
        except (RuntimeError, ValueError):  # the training thread changed a list mid-draw
            pass
        self.root.after(33 if self.trainer else 16, self.loop)

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
        if self.trainer:
            line = f"TRAINING (full speed) - {self.train_status}   fight time {sim.t:4.0f}s  HP {max(sim.hp, 0)}/{MAX_HP}"
        else:
            real = max(1e-6, time.perf_counter() - self.real_start)
            actual = (sim.t - self.sim_start) / real
            line = (f"time {sim.t:5.0f}s   HP {max(sim.hp, 0)}/{MAX_HP}   hits {sim.hits} ({sim.hits / minutes:.1f}/min)   "
                    f"kills {sim.kills}   keys {''.join(sim.keys).upper() or '-':2}   running at {actual:.1f}x")
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
    SimWindow()
    tk.mainloop()
