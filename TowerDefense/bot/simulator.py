"""
Practice arena: watch the bot's real brain play a simulated version of the game.

The world is simulated (no screen reading), but the bot's decisions come from exactly the same
Brain and Tracker it uses in Roblox, including its reaction delay, so you can see how it dodges,
where it gets stuck and what hits it. Speeds 1x/2x/5x/10x; hits are counted.

Open it from the app ("Simulator") or run:  py simulator.py
"""

import math
import random
import time
import tkinter as tk
from tkinter import ttk

from brain import Brain
from vision import Tracker

W, H = 2534, 1239          # same size as the real play area in your screenshots
PR = 26.0                  # player radius
PSPEED = 700.0             # player speed (px/s), as measured in the real game
SIM_DT = 1 / 60
BOT_DT = 1 / 14            # the real bot decides about 14x per second
LATENCY = 0.07             # screenshot -> keys delay
SCENARIOS = {  # shooters, yellow, grunts, tanks, boss
    "Mixed": (4, 2, 4, 1, True),
    "Many shooters": (8, 4, 2, 0, False),
    "Boss": (2, 1, 3, 0, True),
    "Swarm (chasers)": (0, 0, 14, 2, False),
}
COLORS = {"grunt": "#e84a4a", "shooter": "#ffa040", "runner": "#f5d23c", "tank": "#b060f0",
          "boss": "#e84a4a", "bullet_boss": "#e84a4a", "bullet_shooter": "#ffa040",
          "bullet_runner": "#f5d23c", "player": "#a8aab0", "mine": "#ffffff"}
HP = {"grunt": 3, "shooter": 3, "runner": 4, "tank": 12, "boss": 150}
RADIUS = {"grunt": 43, "shooter": 38, "runner": 33, "tank": 63, "boss": 128}
SPEED = {"grunt": 140, "shooter": 150, "runner": 130, "tank": 80, "boss": 90}


class Obj:
    __slots__ = ("kind", "x", "y", "r", "vx", "vy", "hp", "cd", "cd2", "rot", "src")

    def __init__(self, kind, x, y, r, vx=0.0, vy=0.0, hp=1, src=""):
        self.kind, self.x, self.y, self.r, self.vx, self.vy = kind, x, y, r, vx, vy
        self.hp, self.cd, self.cd2, self.rot, self.src = hp, 1.0, 1.0, 0.0, src


class Sim:
    def __init__(self, scenario="Mixed", seed=None, brain_kw=None, oracle=False):
        self.oracle = oracle  # testing: give the brain the true speeds instead of tracked ones
        self.rnd = random.Random(seed)
        self.scenario = scenario
        self.px, self.py = W / 2, H / 2
        self.t, self.hits, self.kills = 0.0, 0, 0
        self.last_hit = -9.0
        self.next_bot = 0.0
        self.keys, self.aim, self.fire = (), None, False
        self.pending = []
        self.shot_cd = 0.0
        self.objs, self.bullets, self.mine = [], [], []
        self.respawns = []  # (time, kind)
        self.tracker, self.brain = Tracker(), Brain(**(brain_kw or {}))
        self.corner_time = 0.0
        n_sh, n_ye, n_gr, n_tk, boss = SCENARIOS[scenario]
        for kind, n in (("shooter", n_sh), ("runner", n_ye), ("grunt", n_gr), ("tank", n_tk)):
            for _ in range(n):
                self.spawn(kind)
        if boss:
            self.spawn("boss")

    def spawn(self, kind):
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
        tracks = self.tracker.update(dets, BOT_DT, (self.px, self.py), 1200 * PR / 13, 260 * PR / 13)
        if self.oracle:
            from vision import Track
            tracks = []
            for o in self.objs + self.bullets:
                t = Track(o.x, o.y, o.r, "enemy_bullet" if o.kind == "bullet" else o.kind, o.vx, o.vy)
                t.age = 10
                tracks.append(t)
        keys, aim, fire = self.brain.think((self.px, self.py, PR), PSPEED, tracks, W, H, latency=LATENCY)
        self.pending.append((self.t + LATENCY, keys, aim, fire))

    # ------------------------------------------------------------------ one tick
    def step(self, dt=SIM_DT):
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

        px, py = self.px, self.py
        for o in self.objs:
            d = math.hypot(px - o.x, py - o.y) or 1
            nx, ny = (px - o.x) / d, (py - o.y) / d
            sp = SPEED[o.kind]
            if o.kind in ("grunt", "tank", "boss"):
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
                self.objs.remove(hit)
                self.kills += 1
                self.respawns.append((self.t + 2.5, hit.kind))
        self.mine = keep
        for when, kind in [r for r in self.respawns if r[0] <= self.t]:
            self.respawns.remove((when, kind))
            self.spawn(kind)
        # getting hit (0.5 s of invulnerability after a hit, like a blink)
        if self.t - self.last_hit > 0.5:
            for o in self.objs + self.bullets:
                if math.hypot(o.x - px, o.y - py) < o.r + PR:
                    self.hits += 1
                    self.last_hit = self.t
                    break
        if min(px, W - px) < 250 and min(py, H - py) < 250:
            self.corner_time += dt
        self.t += dt


def benchmark(scenario, seeds=range(6), seconds=60, oracle=False, **brain_kw):
    """Average hits per minute and corner seconds per minute for a brain setting (no window)."""
    hits = corner = 0.0
    for seed in seeds:
        sim = Sim(scenario, seed=seed, brain_kw=brain_kw, oracle=oracle)
        while sim.t < seconds:
            sim.step()
        hits += sim.hits
        corner += sim.corner_time
    n = len(seeds) * seconds / 60
    return hits / n, corner / n


class SimWindow:
    SCALE = 0.5

    def __init__(self, master=None):
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
        ttk.Button(bar, text="Restart", command=self.restart).pack(side="left", padx=(0, 12))
        self.scen = tk.StringVar(value="Mixed")
        box = ttk.Combobox(bar, textvariable=self.scen, values=list(SCENARIOS), state="readonly", width=16)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _e: self.restart())
        self.info = tk.StringVar()
        tk.Label(bar, textvariable=self.info, bg="#07090d", fg="#e4e7ec", font=("Consolas", 10)).pack(side="left", padx=14)
        self.canvas = tk.Canvas(self.root, width=int(W * self.SCALE), height=int(H * self.SCALE),
                                bg="#05070b", highlightthickness=0)
        self.canvas.pack(padx=10, pady=(0, 10))
        self.restart()
        self.set_speed(1)
        self.last = time.perf_counter()
        self.real_start, self.sim_start = self.last, 0.0
        self.root.after(16, self.loop)

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
        self.sim = Sim(self.scen.get())
        self.real_start, self.sim_start = time.perf_counter(), 0.0

    def loop(self):
        now = time.perf_counter()
        frame_dt = min(0.1, now - self.last)
        self.last = now
        if not self.paused:
            todo = frame_dt * self.speed
            deadline = now + 0.05  # don't freeze the window if the PC can't keep up
            while todo > 1e-9 and time.perf_counter() < deadline:
                step = min(SIM_DT, todo)
                self.sim.step(step)
                todo -= step
        self.draw()
        self.root.after(16, self.loop)

    def draw(self):
        c, s, sim = self.canvas, self.SCALE, self.sim
        c.delete("all")
        for o in sim.objs:
            x, y, r = o.x * s, o.y * s, o.r * s
            col = COLORS[o.kind]
            if o.kind in ("grunt", "tank"):
                c.create_rectangle(x - r * 0.75, y - r * 0.75, x + r * 0.75, y + r * 0.75, outline=col,
                                   width=2 if o.kind == "tank" else 0, fill="" if o.kind == "tank" else col)
            elif o.kind in ("shooter", "runner"):
                c.create_oval(x - r, y - r, x + r, y + r, outline=col)
                c.create_oval(x - r * 0.4, y - r * 0.4, x + r * 0.4, y + r * 0.4, fill=col, outline="")
            else:  # boss
                c.create_rectangle(x - r * 0.35, y - r, x + r * 0.35, y + r, fill=col, outline="")
                c.create_rectangle(x - r, y - r * 0.35, x + r, y + r * 0.35, fill=col, outline="")
        for b in sim.bullets:
            x, y, r = b.x * s, b.y * s, b.r * s
            c.create_oval(x - r, y - r, x + r, y + r, fill=COLORS["bullet_" + b.src], outline="")
        for b in sim.mine:
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
        minutes = max(sim.t, 1e-6) / 60
        real = max(1e-6, time.perf_counter() - self.real_start)
        actual = (sim.t - self.sim_start) / real
        self.info.set(f"time {sim.t:5.0f}s   hits {sim.hits} ({sim.hits / minutes:.1f}/min)   kills {sim.kills}   "
                      f"keys {''.join(sim.keys).upper() or '-':2}   running at {actual:.1f}x")


if __name__ == "__main__":
    SimWindow()
    tk.mainloop()
