"""
Self-training for the bot's dodging behaviour.

The bot's movement is steered by a handful of numbers (how close bullets may come, how much it
fears crowds and walls, ...). Training tries small random changes to those numbers and keeps the
ones that make runs last longer:

- auto: every change is played for a few runs; it's kept if the average run time beats the best so far.
- semi: after every run you're asked "keep or revert?", and your answer is what it learns from.

Everything is stored in config.json under "training", and a history goes to training_log.csv.
"""

import csv
import math
import os
import random
import time

# name: (default, min, max). These are the Brain's class attributes.
PARAMS = {
    "BULLET_MARGIN": (22.0, 8.0, 50.0),     # how close bullets may pass
    "MOB_MARGIN": (60.0, 20.0, 140.0),      # how close mobs may get
    "CROWD_WEIGHT": (2500.0, 300.0, 9000.0),  # how much it avoids groups of mobs
    "WALL_MARGIN": (140.0, 30.0, 280.0),    # distance it tries to keep from walls
    "WALL_WEIGHT": (0.35, 0.05, 2.0),       # how much it cares about that
    "ORBIT_WEIGHT": (150.0, 0.0, 600.0),    # how strongly it runs laps around the middle
}
RUNS_PER_TRY = 2  # auto mode averages this many runs before judging a change
MIN_RUN = 3.0     # runs shorter than this (seconds) are ignored (misfires, restarts)


def defaults():
    return {k: v[0] for k, v in PARAMS.items()}


def mutate(params, rng=random):
    """Nudge one or two of the numbers by up to about +-35%."""
    new = dict(params)
    for name in rng.sample(list(PARAMS), rng.choice([1, 2])):
        _, lo, hi = PARAMS[name]
        value = new[name] if new[name] > 0 else (hi - lo) * 0.05
        new[name] = round(min(hi, max(lo, value * math.exp(rng.gauss(0, 0.3)))), 2)
    return new


class Trainer:
    def __init__(self, cfg, log_path=None):
        self.cfg = cfg
        self.log_path = log_path
        t = cfg.setdefault("training", {})
        t.setdefault("mode", "off")  # off / semi / auto
        t.setdefault("best", defaults())
        t.setdefault("best_score", None)  # average run time (s) of the best settings
        t.setdefault("best_runs", 0)
        t.setdefault("candidate", None)
        t.setdefault("cand_scores", [])
        for k, v in defaults().items():  # settings saved by an older version
            t["best"].setdefault(k, v)
        self.t = t

    @property
    def mode(self):
        return self.t["mode"]

    def params_for_next_run(self):
        """The numbers the bot should use for the coming run."""
        if self.mode != "off" and self.t["candidate"] is None:
            self.t["candidate"] = mutate(self.t["best"])
            self.t["cand_scores"] = []
        if self.mode != "off":
            return dict(self.t["candidate"])
        return dict(self.t["best"])

    def run_finished(self, seconds):
        """Call when a run ends in death. Returns (message, needs_answer)."""
        if self.mode == "off":
            self._update_best_score(seconds)
            return f"Run lasted {seconds:.0f}s.", False
        if seconds < MIN_RUN:
            return f"Run of {seconds:.1f}s ignored (too short to judge).", False
        self.t["cand_scores"].append(seconds)
        best = self.t["best_score"]
        best_txt = f"best average {best:.0f}s" if best else "no best yet"
        if self.mode == "semi":
            return (f"Run lasted {seconds:.0f}s with changed settings ({best_txt}). "
                    f"Changes: {self.describe_change()}. Keep them?"), True
        # auto
        scores = self.t["cand_scores"]
        if len(scores) < RUNS_PER_TRY:
            return f"Run lasted {seconds:.0f}s; testing this change for {RUNS_PER_TRY - len(scores)} more run(s).", False
        avg = sum(scores) / len(scores)
        keep = best is None or avg > best * 1.05
        return self.decide(keep, avg), False

    def decide(self, keep, score=None):
        """Keep or throw away the settings that were just tried."""
        scores = self.t["cand_scores"]
        score = score if score is not None else (sum(scores) / len(scores) if scores else 0.0)
        change = self.describe_change()
        if keep:
            self.t["best"] = self.t["candidate"]
            self.t["best_score"] = score
            self.t["best_runs"] = len(scores)
            msg = f"Kept: {change} (average {score:.0f}s)."
        else:
            msg = f"Reverted: {change} (average {score:.0f}s)."
            if self.t["best_score"]:
                # One lucky run shouldn't block all future changes, so the record slowly fades.
                self.t["best_score"] *= 0.99
        self._log(keep, score, change)
        self.t["candidate"] = None
        self.t["cand_scores"] = []
        return msg

    def reset(self):
        self.t.update({"best": defaults(), "best_score": None, "best_runs": 0, "candidate": None, "cand_scores": []})

    def describe_change(self):
        cand = self.t["candidate"] or {}
        parts = [f"{k.lower()} {self.t['best'][k]:g} -> {cand[k]:g}" for k in PARAMS
                 if k in cand and cand[k] != self.t["best"][k]]
        return ", ".join(parts) or "no change"

    def _update_best_score(self, seconds):
        # Training off: runs still refine how good the current best settings are.
        if seconds < MIN_RUN:
            return
        n, s = self.t["best_runs"], self.t["best_score"]
        self.t["best_score"] = seconds if s is None else (s * n + seconds) / (n + 1)
        self.t["best_runs"] = n + 1

    def _log(self, kept, score, change):
        if not self.log_path:
            return
        new = not os.path.exists(self.log_path)
        try:
            with open(self.log_path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "mode", "kept", "avg_seconds", "runs", "change"] + list(PARAMS))
                cand = self.t["candidate"] or {}
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), self.mode, kept, round(score, 1),
                            len(self.t["cand_scores"]), change] + [cand.get(k) for k in PARAMS])
        except OSError:
            pass
