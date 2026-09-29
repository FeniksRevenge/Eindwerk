"""
Screen reading: find the player, mobs and enemy bullets in a screenshot of the play area,
and track them between frames so we know how fast and where they are moving.

Everything is found by color. The colors (and the normal size of each thing) come from
config.json, which `swarm_bot.py calibrate` creates.
"""

import math

import cv2
import numpy as np

# Things the calibration asks you to click on, in this order.
CLASSES = ["player", "enemy_bullet", "shooter_bullet", "grunt", "runner", "shooter", "tank", "boss"]
MOB_KINDS = ["grunt", "runner", "shooter", "tank", "boss"]
CLASS_HELP = {
    "player": "YOU (the player ball)",
    "enemy_bullet": "an ENEMY BULLET (e.g. the boss's red circles)",
    "shooter_bullet": "a bullet from the ORANGE shooter (skip if it looks the same as the other bullets)",
    "grunt": "a RED mob (grunt)",
    "runner": "a YELLOW mob (runner)",
    "shooter": "an ORANGE mob (shooter)",
    "tank": "a BLUE mob (tank)",
    "boss": "the BOSS",
}

DEFAULT_TOLERANCE = [30, 14, 14]  # allowed difference in L, a, b (OpenCV 8-bit Lab)


def bgr_to_lab_pixel(bgr):
    px = np.uint8([[bgr]])
    return [int(v) for v in cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0, 0]]


def color_mask(lab_img, lab, tol):
    lab = np.array(lab, dtype=np.int32)
    tol = np.array(tol, dtype=np.int32)
    lo = np.clip(lab - tol, 0, 255).astype(np.uint8)
    hi = np.clip(lab + tol, 0, 255).astype(np.uint8)
    return cv2.inRange(lab_img, lo, hi)


def measure_blob(bgr_img, x, y, tol=DEFAULT_TOLERANCE):
    """Color and size of the blob under (x, y). Used by calibration when you click something."""
    h, w = bgr_img.shape[:2]
    patch = bgr_img[max(0, y - 2):y + 3, max(0, x - 2):x + 3].reshape(-1, 3)
    bgr = np.median(patch, axis=0).astype(np.uint8)
    lab = bgr_to_lab_pixel(bgr)
    mask = color_mask(cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB), lab, tol)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    comp = labels[y, x]
    if comp == 0:
        return lab, 0.0
    bw, bh = stats[comp, cv2.CC_STAT_WIDTH], stats[comp, cv2.CC_STAT_HEIGHT]
    return lab, max(bw, bh) / 2.0


class Detector:
    """Finds things by color, then by size.

    In the Roblox game the basic mob, the boss and the boss's bullets are all the same red,
    so when several classes share a color each blob goes to the class whose normal size
    is closest (a small red circle is a bullet, a big red cross is the boss).
    """

    def __init__(self, cfg):
        self.scale = int(cfg.get("downscale", 2))
        self.tol = cfg.get("tolerance", DEFAULT_TOLERANCE)
        groups = {}
        for name, c in cfg["colors"].items():
            if c and c.get("lab") and float(c.get("radius", 0)) > 0:
                groups.setdefault(tuple(c["lab"]), []).append((name, float(c["radius"])))
        self.groups = list(groups.items())

    def blobs(self, lab_img, lab):
        """(x, y, radius) of every roughly solid blob of this color, in downscaled pixels."""
        mask = color_mask(lab_img, lab, self.tol)
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out = []
        for i in range(1, n):
            bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]
            # Skip thin lines (the aim line) and text-like shapes: real things fill their box.
            if max(bw, bh) > 3 * max(1, min(bw, bh)) or area < 0.3 * bw * bh:
                continue
            out.append((cents[i][0], cents[i][1], max(bw, bh) / 2.0))
        return out

    def detect(self, bgr):
        """Returns {class name: [(x, y, radius), ...]} in full-size pixel coordinates."""
        s = self.scale
        small = cv2.resize(bgr, (bgr.shape[1] // s, bgr.shape[0] // s), interpolation=cv2.INTER_NEAREST) if s > 1 else bgr
        lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
        out = {name: [] for name in CLASSES}
        for lab_c, members in self.groups:
            for (x, y, r) in self.blobs(lab, lab_c):
                x, y, r = x * s + s / 2, y * s + s / 2, r * s
                # Pick the class with the closest normal size (compared as a ratio).
                name, r_exp = min(members, key=lambda m: abs(math.log(max(r, 0.5) / m[1])))
                smallest = min(m[1] for m in members)
                if r < smallest * 0.45:
                    continue  # specks and explosion particles
                if name in ("enemy_bullet", "shooter_bullet", "player") and r > r_exp * 2:
                    continue
                if name == "player" and not (0.65 * r_exp <= r <= 1.6 * r_exp):
                    continue  # HUD text is gray too, but much smaller than the player
                if name == "shooter_bullet":
                    name = "enemy_bullet"
                out[name].append((x, y, r))
        return out


class Track:
    __slots__ = ("x", "y", "vx", "vy", "r", "kind", "age", "missing")

    def __init__(self, x, y, r, kind, vx=0.0, vy=0.0):
        self.x, self.y, self.r, self.kind = x, y, r, kind
        self.vx, self.vy = vx, vy
        self.age = 0
        self.missing = 0


class Tracker:
    """Matches this frame's blobs to last frame's so every mob/bullet gets a velocity."""

    def __init__(self):
        self.tracks = []

    def update(self, dets, dt, player_xy, max_speed, new_bullet_speed):
        px, py = player_xy
        new_tracks = []
        for kind in MOB_KINDS + ["enemy_bullet"]:
            old = [t for t in self.tracks if t.kind == kind]
            used = set()
            for (x, y, r) in dets.get(kind, []):
                best, best_d = None, max_speed * dt + r + 6
                for i, t in enumerate(old):
                    if i in used:
                        continue
                    d = math.hypot(t.x + t.vx * dt - x, t.y + t.vy * dt - y)
                    if d < best_d:
                        best, best_d = i, d
                if best is not None:
                    used.add(best)
                    t = old[best]
                    if dt > 0:
                        a = 0.5  # smoothing
                        t.vx = (1 - a) * t.vx + a * (x - t.x) / dt
                        t.vy = (1 - a) * t.vy + a * (y - t.y) / dt
                    t.x, t.y, t.r = x, y, r
                    t.age += 1
                    t.missing = 0
                    new_tracks.append(t)
                else:
                    # Brand new thing. A new bullet is almost always flying at the player.
                    vx = vy = 0.0
                    if kind == "enemy_bullet":
                        d = math.hypot(px - x, py - y) or 1.0
                        vx, vy = (px - x) / d * new_bullet_speed, (py - y) / d * new_bullet_speed
                    new_tracks.append(Track(x, y, r, kind, vx, vy))
            # Keep things that vanished for a frame or two (flicker, overlap) at their predicted spot.
            for i, t in enumerate(old):
                if i not in used and t.missing < 2:
                    t.missing += 1
                    t.x += t.vx * dt
                    t.y += t.vy * dt
                    new_tracks.append(t)
        self.tracks = new_tracks
        return self.tracks
