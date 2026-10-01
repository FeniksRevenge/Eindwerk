"""
Getting better run after run: what the bot remembers between runs (in learned.json next to the app).

  - Room to keep per enemy: every time you get hit, it looks at what hit you (the closest thing just
    before your HP dropped) and keeps more room from that kind from then on. Room it doesn't need
    slowly goes back to normal while you play without getting hit by that kind (too much room
    gets you cornered), so it settles where the hits stop.
  - How fast things are: the walking speed of every enemy kind and the speed of bullets, measured
    every run, so a new enemy is predicted right from the first moment it shows up.
  - Its play style, by trying things out: every few runs it tries a small change (e.g. keep 20% more
    room from bullets, or stay further from walls) for 3 runs and keeps it only if those runs lasted
    clearly longer than its usual runs. Runs vary a lot, so this is slow: a night gives it ~10 tries.
  - A list of every run (how long, how many hits, from what, which style), to see if it's getting better.
"""

import json
import math
import os
import time

CAUSES = ("bullet", "grunt", "tiny", "tank", "yellow", "shooter", "boss")
ROOM_STEP = 0.08        # more room after a hit (x the normal room)
ROOM_MAX = 1.6          # never more than this x the normal room
ROOM_RELAX = 600.0      # seconds of play without hits from a kind to lose ~63% of its extra room
# play style: multipliers on the planner's weights, tuned by trying (see above)
STYLE_KEYS = ("bullet_room", "mob_room", "walls", "laps", "crowd")
STYLE_RANGE = (0.6, 1.8)
STYLE_STEP = 1.2        # a try changes one of them by this factor (up or down)
TRIAL_RUNS = 4          # runs per try
BASE_RUNS = 8           # compare with this many recent runs of the current style
BETTER = 1.15           # a try is kept if its runs lasted this much longer on average
SPEED_KINDS = ("grunt", "tiny", "tank", "yellow", "shooter", "boss")


class Learner:
    def __init__(self, path):
        self.path = path
        self.room = {k: 1.0 for k in CAUSES}
        self.speed = {}           # kind -> walking speed as a fraction of yours
        self.bullet_speed = None  # as a fraction of the window height per second
        self.style = {k: 1.0 for k in STYLE_KEYS}
        self.base_runs = []       # run lengths (s) with the current style
        self.trial = None         # {"key", "factor", "runs"}: a style change being tried
        self.next_try = 0         # tries go through every change in turn
        self.kept = 0             # how many tries were kept
        self.runs = []
        self.load()
        self.new_run()

    # ------------------------------------------------------------------ saving
    def load(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        for k, v in d.get("room", {}).items():
            if k in self.room:
                self.room[k] = min(max(float(v), 1.0), ROOM_MAX)
        self.speed = {k: float(v) for k, v in d.get("speed", {}).items() if k in SPEED_KINDS and 0.2 < v < 2.0}
        bs = d.get("bullet_speed")
        self.bullet_speed = float(bs) if bs and 0.1 < bs < 3.0 else None
        self.runs = list(d.get("runs", []))[-1000:]
        for k, v in d.get("style", {}).items():
            if k in self.style:
                self.style[k] = min(max(float(v), STYLE_RANGE[0]), STYLE_RANGE[1])
        self.base_runs = [float(v) for v in d.get("base_runs", [])][-BASE_RUNS:]
        t = d.get("trial")
        if isinstance(t, dict) and t.get("key") in STYLE_KEYS:
            self.trial = {"key": t["key"], "factor": float(t["factor"]), "runs": [float(v) for v in t["runs"]]}
        self.kept = int(d.get("kept", 0))
        self.next_try = int(d.get("next_try", 0))

    def save(self):
        d = {"room": {k: round(v, 3) for k, v in self.room.items()},
             "speed": {k: round(v, 3) for k, v in self.speed.items()},
             "bullet_speed": self.bullet_speed and round(self.bullet_speed, 3),
             "style": {k: round(v, 3) for k, v in self.style.items()},
             "base_runs": self.base_runs, "trial": self.trial, "kept": self.kept,
             "next_try": self.next_try,
             "runs": self.runs[-1000:]}
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(d, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def reset(self):
        self.room = {k: 1.0 for k in CAUSES}
        self.speed, self.bullet_speed, self.runs = {}, None, []
        self.style = {k: 1.0 for k in STYLE_KEYS}
        self.base_runs, self.trial, self.kept, self.next_try = [], None, 0, 0
        self.new_run()
        self.save()

    # ------------------------------------------------------------------ play style
    def current_style(self):
        """The style to play this run with (the current one, or the one being tried)."""
        st = dict(self.style)
        if self.trial is not None:
            st[self.trial["key"]] = self._tried_value()
        return st

    def _tried_value(self):
        k = self.trial["key"]
        return min(max(self.style[k] * self.trial["factor"], STYLE_RANGE[0]), STYLE_RANGE[1])

    def _style_result(self, secs):
        """A finished game: count it for the current style or the try, and decide about the try."""
        note = ""
        if self.trial is None:
            self.base_runs = (self.base_runs + [secs])[-BASE_RUNS:]
        else:
            self.trial["runs"].append(secs)
            if len(self.trial["runs"]) >= TRIAL_RUNS:
                k, tried = self.trial["key"], self.trial["runs"]
                base = sum(self.base_runs) / len(self.base_runs)
                new = sum(tried) / len(tried)
                if new > BETTER * base:
                    self.style[k] = self._tried_value()
                    self.base_runs = list(tried)
                    self.kept += 1
                    note = f"kept: {k} x{self.style[k]:.2f} (avg {_mmss(new)} vs {_mmss(base)})"
                else:
                    note = f"dropped: {k} x{self.trial['factor']:.2f} (avg {_mmss(new)} vs {_mmss(base)})"
                self.trial = None
                return note  # play one normal run before the next try
        if self.trial is None and len(self.base_runs) >= 3:
            for _ in range(2 * len(STYLE_KEYS)):  # every key up, every key down, in turn
                i = self.next_try % (2 * len(STYLE_KEYS))
                self.next_try += 1
                k, f = STYLE_KEYS[i // 2], (STYLE_STEP if i % 2 == 0 else 1 / STYLE_STEP)
                if STYLE_RANGE[0] - 1e-6 <= self.style[k] * f <= STYLE_RANGE[1] + 1e-6:
                    self.trial = {"key": k, "factor": f, "runs": []}
                    break
        return note

    # ------------------------------------------------------------------ during a run
    def new_run(self):
        self.run = {"start": time.strftime("%Y-%m-%d %H:%M:%S"), "secs": 0.0, "hits": 0, "causes": {},
                    "style": {k: round(v, 2) for k, v in self.current_style().items() if abs(v - 1) > 1e-3}}
        self.samples = {k: [] for k in SPEED_KINDS}
        self.bullet_samples = []

    def played(self, dt, tracks, V, H):
        """Call every step while you're in a game: relaxes the room and collects speeds."""
        self.run["secs"] += dt
        f = math.exp(-dt / ROOM_RELAX)
        for k in self.room:
            self.room[k] = 1.0 + (self.room[k] - 1.0) * f
        for t in tracks:
            if t.age < 5 or t.missing:
                continue
            if t.kind == "bullet":
                if len(self.bullet_samples) < 5000:
                    self.bullet_samples.append(t.speed / H)
            elif t.kind in self.samples and len(self.samples[t.kind]) < 5000 and V > 0:
                self.samples[t.kind].append(t.speed / V)

    def hit(self, cause):
        self.run["hits"] += 1
        self.run["causes"][cause] = self.run["causes"].get(cause, 0) + 1
        if cause in self.room:
            self.room[cause] = min(ROOM_MAX, self.room[cause] + ROOM_STEP)

    def end_run(self, how):
        """how: "game over", "stopped" or "lost"."""
        if self.run["secs"] < 5:
            self.new_run()
            return None
        for k, s in self.samples.items():
            if len(s) >= 30:
                s = sorted(s)
                top = s[int(0.8 * (len(s) - 1))]  # walking at you, not stuck behind others
                if 0.2 < top < 2.0:
                    self.speed[k] = top if k not in self.speed else 0.7 * self.speed[k] + 0.3 * top
        if len(self.bullet_samples) >= 30:
            s = sorted(self.bullet_samples)
            med = s[len(s) // 2]
            if 0.1 < med < 3.0:
                self.bullet_speed = med if self.bullet_speed is None else 0.7 * self.bullet_speed + 0.3 * med
        run = dict(self.run, secs=round(self.run["secs"]), end=how)
        if how == "game over":
            run["style_note"] = self._style_result(self.run["secs"])
        self.runs.append(run)
        self.save()
        self.new_run()
        return run

    # ------------------------------------------------------------------ for the window
    def summary(self):
        done = [r for r in self.runs if r.get("end") == "game over"]
        if not done:
            text = "no finished runs yet"
        else:
            last = done[-10:]
            avg = sum(r["secs"] for r in last) / len(last)
            best = max(r["secs"] for r in done)
            text = (f"{len(done)} runs, last {len(last)} avg {_mmss(avg)}, best {_mmss(best)}")
        extra = ", ".join(f"{k} x{v:.2f}" for k, v in self.room.items() if v > 1.02)
        style = ", ".join(f"{k} x{v:.2f}" for k, v in self.style.items() if abs(v - 1) > 1e-3)
        text += f"; style: {style or 'normal'} ({self.kept} changes kept)"
        if self.trial is not None:
            text += (f"; trying {self.trial['key']} x{self._tried_value():.2f} "
                     f"(run {len(self.trial['runs']) + 1}/{TRIAL_RUNS})")
        return text + (f"; more room from: {extra}" if extra else "")


def _mmss(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}"
