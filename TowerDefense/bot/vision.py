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
CLASSES = ["player", "enemy_bullet", "shooter_bullet", "yellow_bullet", "grunt", "shooter", "runner", "tank",
           "tank_mini", "boss", "health"]
BULLET_CLASSES = ("enemy_bullet", "shooter_bullet", "yellow_bullet")
MOB_KINDS = ["grunt", "runner", "shooter", "tank", "tank_mini", "boss"]
CLASS_HELP = {
    "player": "YOU (the gray ball)",
    "enemy_bullet": "a RED bullet (the boss's red balls)",
    "shooter_bullet": "an ORANGE bullet (from the orange shooter)",
    "grunt": "the RED square (basic mob)",
    "shooter": "the ORANGE ball (shooter, not its ring)",
    "tank": "a PURPLE tank",
    "tank_mini": "one of the TINY mobs that come out of a dead tank",
    "boss": "the BOSS (red cross)",
    "health": "a GREEN health circle",
    "runner": "the YELLOW mob (the one that shoots in all directions)",
    "yellow_bullet": "a bullet from the YELLOW mob",
}

DEFAULT_TOLERANCE = [30, 14, 14]  # allowed difference in L, a, b (OpenCV 8-bit Lab)

# Colors and sizes measured from real screenshots of the Roblox game (a 2534x1239 play area).
# Sizes are scaled to your play area's height when the preset is applied.
PRESET = {
    "ref_height": 1239,
    "colors": {
        "player": {"lab": [172, 128, 123], "radius": 26.5},
        "enemy_bullet": {"lab": [131, 191, 167], "radius": 14.5},
        "shooter_bullet": {"lab": [189, 156, 192], "radius": 13.0},
        "grunt": {"lab": [139, 191, 165], "radius": 43.0},
        "shooter": {"lab": [189, 156, 192], "radius": 14.0},
        "tank": {"lab": [151, 190, 65], "radius": 63.0},
        "tank_mini": {"lab": [183, 171, 85], "radius": 29.5},
        "boss": {"lab": [131, 191, 167], "radius": 128.0},
        "health": {"lab": [217, 64, 174], "radius": 9.0},
    },
}


def bgr_to_lab_pixel(bgr):
    px = np.uint8([[bgr]])
    return [int(v) for v in cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0, 0]]


def color_mask(lab_img, lab, tol):
    lab = np.array(lab, dtype=np.int32)
    tol = np.array(tol, dtype=np.int32)
    lo = np.clip(lab - tol, 0, 255).astype(np.uint8)
    hi = np.clip(lab + tol, 0, 255).astype(np.uint8)
    return cv2.inRange(lab_img, lo, hi)


def background_lab(bgr_img):
    """The most common color of the image = the background."""
    small = cv2.resize(bgr_img, (64, 36), interpolation=cv2.INTER_AREA)
    return np.median(cv2.cvtColor(small, cv2.COLOR_BGR2LAB).reshape(-1, 3), axis=0)


def measure_blob(bgr_img, x, y, tol=DEFAULT_TOLERANCE):
    """Color and size of the thing under (x, y). Used by calibration when you click something.

    Returns (lab, radius), or (None, 0) when the click landed on background (e.g. next to a
    thin ring), so a bad click can't teach the bot that the background is an enemy.
    """
    lab_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
    bg = background_lab(bgr_img)
    patch = lab_img[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3).astype(np.float64)
    colored = patch[np.linalg.norm(patch - bg, axis=1) > 35]  # ignore background pixels around the click
    if len(colored) < 3:
        return None, 0.0
    lab = [int(v) for v in np.median(colored, axis=0)]
    mask = color_mask(lab_img, lab, tol)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    # The component under the click, or the nearest colored pixel's component.
    ys, xs = np.nonzero(labels[max(0, y - 3):y + 4, max(0, x - 3):x + 4])
    if len(xs) == 0:
        return None, 0.0
    comp = labels[max(0, y - 3) + ys[0], max(0, x - 3) + xs[0]]
    bw, bh = stats[comp, cv2.CC_STAT_WIDTH], stats[comp, cv2.CC_STAT_HEIGHT]
    radius = max(bw, bh) / 2.0
    if radius > 0.3 * min(bgr_img.shape[:2]) or radius < 3:
        return None, 0.0  # screen-sized (background) or a sliver of a thin ring
    return lab, radius


class Detector:
    """Finds things by color, then by size.

    In the Roblox game the basic mob, the boss and the boss's bullets are all the same red,
    so when several classes share a color each blob goes to the class whose normal size
    is closest (a small red circle is a bullet, a big red cross is the boss).
    """

    def __init__(self, cfg):
        self.scale = int(cfg.get("downscale", 2))
        self.tol = cfg.get("tolerance", DEFAULT_TOLERANCE)
        # Group classes whose colors are practically the same (calibration clicks on the same red
        # rarely give identical numbers), so one red blob is never reported as two things.
        self.groups = []  # [([lab, ...], [(name, radius), ...])]
        tol = np.array(self.tol)
        for name, c in cfg["colors"].items():
            if not (c and c.get("lab") and float(c.get("radius", 0)) > 0):
                continue
            lab = np.array(c["lab"])
            for labs, members in self.groups:
                if any(np.all(np.abs(lab - np.array(other)) <= tol * 0.6) for other in labs):
                    labs.append(c["lab"])
                    members.append((name, float(c["radius"])))
                    break
            else:
                self.groups.append(([c["lab"]], [(name, float(c["radius"]))]))

    def blobs(self, lab_img, labs, min_fill=0.3):
        """(x, y, radius) of every roughly solid blob of these colors, in downscaled pixels."""
        mask = color_mask(lab_img, labs[0], self.tol)
        for lab in labs[1:]:
            mask |= color_mask(lab_img, lab, self.tol)
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out = []
        for i in range(1, n):
            bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]
            # Skip thin lines (the aim line) and text-like shapes: real things fill their box.
            if max(bw, bh) > 3 * max(1, min(bw, bh)) or area < min_fill * bw * bh:
                continue
            if max(bw, bh) > 0.35 * min(lab_img.shape[:2]):
                continue  # screen-sized: a color that matches the background, not a mob
            out.append((cents[i][0], cents[i][1], max(bw, bh) / 2.0))
        return out

    def detect(self, bgr):
        """Returns {class name: [(x, y, radius), ...]} in full-size pixel coordinates."""
        s = self.scale
        small = cv2.resize(bgr, (bgr.shape[1] // s, bgr.shape[0] // s), interpolation=cv2.INTER_NEAREST) if s > 1 else bgr
        lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
        out = {name: [] for name in CLASSES}
        for labs, members in self.groups:
            # Health pickups may be drawn as a ring, so allow hollow shapes for them.
            min_fill = 0.08 if any(m[0] == "health" for m in members) else 0.3
            for (x, y, r) in self.blobs(lab, labs, min_fill):
                x, y, r = x * s + s / 2, y * s + s / 2, r * s
                # Pick the class with the closest normal size (compared as a ratio).
                name, r_exp = min(members, key=lambda m: abs(math.log(max(r, 0.5) / m[1])))
                smallest = min(m[1] for m in members)
                if r < smallest * 0.45:
                    continue  # specks and explosion particles
                if (name in BULLET_CLASSES or name == "player") and r > r_exp * 2:
                    continue
                if name == "player" and not (0.65 * r_exp <= r <= 1.6 * r_exp):
                    continue  # HUD text is gray too, but much smaller than the player
                if name in BULLET_CLASSES:
                    name = "enemy_bullet"  # all bullets are dodged the same way
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
        for kind in MOB_KINDS + ["enemy_bullet", "health"]:
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
                    if kind == "enemy_bullet":  # health pickups stay put
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


DRAW_COLORS = {"player": (140, 230, 120), "enemy_bullet": (80, 80, 255), "shooter_bullet": (80, 80, 255),
               "yellow_bullet": (80, 80, 255),
               "grunt": (60, 60, 230), "runner": (90, 220, 230), "shooter": (50, 150, 255),
               "tank": (200, 80, 160), "tank_mini": (230, 120, 200), "boss": (200, 40, 200),
               "health": (80, 255, 80)}


def annotate(frame, dets, player=None, keys=None, aim=None, extra=""):
    """Copy of the frame with what the bot sees and decided drawn on top."""
    img = frame.copy()
    for name, items in dets.items():
        for (x, y, r) in items:
            cv2.circle(img, (int(x), int(y)), int(r) + 3, DRAW_COLORS[name], 2)
            cv2.putText(img, name, (int(x - r), int(y - r - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, DRAW_COLORS[name], 1)
    if player is not None:
        x, y, r = player
        cv2.circle(img, (int(x), int(y)), int(r) + 8, (255, 255, 255), 3)
        cv2.putText(img, "BOT THINKS THIS IS YOU", (int(x - r), int(y + r + 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if aim is not None:
            cv2.line(img, (int(x), int(y)), (int(aim[0]), int(aim[1])), (0, 255, 255), 1)
            cv2.drawMarker(img, (int(aim[0]), int(aim[1])), (0, 255, 255), cv2.MARKER_CROSS, 18, 2)
    counts = "  ".join(f"{n}:{len(v)}" for n, v in dets.items() if v) or "nothing found"
    info = f"keys: {''.join(keys).upper() if keys else '-'}   {counts}   {extra}"
    cv2.rectangle(img, (0, 0), (img.shape[1], 30), (0, 0, 0), -1)
    cv2.putText(img, info, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 255, 140), 1, cv2.LINE_AA)
    return img

