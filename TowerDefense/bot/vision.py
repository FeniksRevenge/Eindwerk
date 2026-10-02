"""
Seeing: find the player and everything dangerous in a screenshot of the Roblox window.

All colors were measured from screenshots of the game. All sizes are fractions of the window's inside
height (they were measured in a window 1116 pixels high), so any window size works.

Kinds of things it reports:
    bullet   red (boss), orange (shooter) and yellow (yellow mob) balls flying in straight lines
    grunt    red square              shooter  orange ball in a thin ring (keeps its distance)
    yellow   yellow square in a ring (walks at you, fires rotating rings of bullets)
    tank     big hollow purple square           tiny   small light-purple square (fast)
    boss     big red cross                       health green circle (+HP, disappears after a while)
"""

import math

import cv2
import numpy as np

REF_H = 1116.0  # window inside height the sizes below were measured at

# Colors in OpenCV 8-bit Lab, per group of things that share a color.
COLORS = {
    "red": [[126, 187, 163], [138, 189, 163], [130, 190, 165]],   # bullets, grunts, boss
    "orange": [[181, 153, 186]],                                   # shooter's ball and its bullets
    "yellow": [[225, 123, 198], [220, 123, 196]],                  # yellow mob and its bullets
    "tank": [[148, 188, 67]],
    "tiny": [[180, 170, 86]],
    "health": [[217, 64, 174]],
    "white": [[235, 128, 127]],                                    # the UFO's saucer
    "gray": [[172, 128, 123]],                                     # the player's ball
}
TOLERANCE = {"white": [20, 6, 6], "gray": [16, 5, 6]}
DEFAULT_TOL = [28, 14, 14]

# Radii (pixels at REF_H).
R_BULLET_MAX = 17.0     # red/orange/yellow balls up to this size are bullets (bullets ~10-11, mobs 24+)
R_BOSS_MIN = 70.0       # red things bigger than this are the boss (~100); grunts are 28-38
R_MIN = 4.0             # specks smaller than this are ignored
R_TEXT_MAX = 15.0       # floating score text letters are smaller than this
R_BULLET_MIN = 7.5      # smaller balls are chat emojis (the orange suns), not bullets
R_PLAYER_BALL = (11.0, 30.0)   # the player's gray ball (~19)
R_SAUCER = (22.0, 56.0)        # the UFO's white saucer (~37)
HIT_FACTOR = 1.5               # player's danger radius = this x its ball radius (the saucer sticks out)

FG_LEVEL = 60  # a pixel with any channel brighter than this is "something" (background ~ (8, 5, 4))
_BIN_LAB = None


def _bin_lab():
    """Lab color of every 64x64x64 BGR bin (built once)."""
    global _BIN_LAB
    if _BIN_LAB is None:
        v = (np.arange(64, dtype=np.int32) << 2) + 2
        b, g, r = np.meshgrid(v, v, v, indexing="ij")
        bgr = np.stack([b, g, r], -1).astype(np.uint8).reshape(512, 512, 3)
        _BIN_LAB = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.int16)
    return _BIN_LAB


GROUPS = list(COLORS)  # group id = index + 1


def build_lut():
    """Every possible color -> the group it belongs to (0 = nothing)."""
    bins = _bin_lab()
    best = np.full(len(bins), np.inf, np.float32)
    lut = np.zeros(len(bins), np.uint8)
    for gid, name in enumerate(GROUPS, 1):
        tol = np.array(TOLERANCE.get(name, DEFAULT_TOL), np.float32)
        for lab in COLORS[name]:
            d = (np.abs(bins - np.array(lab, np.int16)) / tol).max(axis=1)
            take = (d <= 1.0) & (d < best)
            best[take] = d[take]
            lut[take] = gid
    return lut


def solidity(sel, area):
    """Area / area of the convex outline: balls and squares ~0.9+, letters and rings much lower."""
    if area < 12:
        return 1.0
    contours, _ = cv2.findContours(sel.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 1.0
    hull = cv2.contourArea(cv2.convexHull(max(contours, key=cv2.contourArea)))
    return min(1.0, area / hull) if hull > 0 else 1.0


class Blob:
    __slots__ = ("x", "y", "r", "w", "h", "bx", "by", "area", "fill", "solid")

    def __init__(self, x, y, r, w, h, bx, by, area, fill, solid):
        self.x, self.y, self.r, self.w, self.h = x, y, r, w, h
        self.bx, self.by, self.area, self.fill, self.solid = bx, by, area, fill, solid

    @property
    def aspect(self):
        return max(self.w, self.h) / max(1.0, min(self.w, self.h))

    def round_ball(self):
        """Looks like a ball (bullets): about as wide as high, fills its box like a circle, solid."""
        return self.aspect <= 1.35 and self.fill >= 0.55 and self.solid >= 0.8


class Thing:
    __slots__ = ("kind", "x", "y", "r", "src")

    def __init__(self, kind, x, y, r, src=""):
        self.kind, self.x, self.y, self.r = kind, x, y, r
        self.src = src  # bullets: their color ("red", "orange", "yellow")

    def __repr__(self):
        return f"{self.kind}({self.x:.0f},{self.y:.0f},r{self.r:.0f})"


class Detector:
    def __init__(self, scale=None):
        self.fixed_scale = scale  # None: pick by window size (big windows are looked at smaller)
        self.s = scale or 2
        self.lut = build_lut()

    # ------------------------------------------------------------------ blobs
    def blobs(self, bgr):
        """{group name: [Blob]} in full-size pixels."""
        H, W = bgr.shape[:2]
        k = H / REF_H
        s = self.s = self.fixed_scale or max(2, int(round(H / 480)))
        small = cv2.resize(bgr, (W // s, H // s), interpolation=cv2.INTER_NEAREST) if s > 1 else bgr
        b, g, r = cv2.split(small)
        _, fg = cv2.threshold(cv2.max(cv2.max(b, g), r), FG_LEVEL, 1, cv2.THRESH_BINARY)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
        min_side = max(2, int(2 * R_MIN * k / s))
        out = {name: [] for name in GROUPS}
        lut = self.lut
        for i in np.nonzero(np.maximum(stats[:, 2], stats[:, 3]) >= min_side)[0]:
            if i == 0:
                continue
            x0, y0, w, h = (int(v) for v in stats[i, :4])
            if max(w, h) < 12:
                # small spot: its middle pixel decides if it's worth a closer look (skips the stars
                # and most HUD/chat letters cheaply)
                c = small[y0 + h // 2, x0 + w // 2]
                if lut[((int(c[0]) >> 2) << 12) | ((int(c[1]) >> 2) << 6) | (int(c[2]) >> 2)] == 0:
                    continue
            crop = small[y0:y0 + h, x0:x0 + w].astype(np.int32)
            grp = lut[((crop[..., 0] >> 2) << 12) | ((crop[..., 1] >> 2) << 6) | (crop[..., 2] >> 2)]
            grp[labels[y0:y0 + h, x0:x0 + w] != i] = 0
            for gid in np.unique(grp):
                if gid == 0:
                    continue
                m, cl, cs, cc = cv2.connectedComponentsWithStats((grp == gid).astype(np.uint8), connectivity=8)
                for j in range(1, m):
                    bx, by, bw, bh, area = (int(v) for v in cs[j])
                    if max(bw, bh) < min_side:
                        continue
                    sel = cl[by:by + bh, bx:bx + bw] == j
                    rr = max(bw, bh) / 2.0 * s
                    solid = solidity(sel, area) if rr <= 45 * k else 1.0
                    out[GROUPS[gid - 1]].append(Blob((x0 + cc[j][0]) * s + s / 2, (y0 + cc[j][1]) * s + s / 2, rr,
                                                     bw * s, bh * s, (x0 + bx) * s, (y0 + by) * s, area * s * s,
                                                     area / float(bw * bh), solid))
        return out

    # ------------------------------------------------------------------ things
    def detect(self, bgr):
        """(player, things): player = (x, y, hit_radius) or None; things = [Thing]."""
        H = bgr.shape[0]
        k = H / REF_H
        bl = self.blobs(bgr)
        things = []
        text = _text_pieces(bl, k)

        for b in bl["red"]:
            if id(b) in text or b.r < R_BULLET_MIN * k:
                continue
            if b.fill > 0.85 and b.h < 0.03 * H and b.aspect >= 1.3 and b.y > 0.85 * H:
                continue  # the boss's health bar at the bottom
            if b.r < R_BULLET_MAX * k:
                if b.round_ball():
                    things.append(Thing("bullet", b.x, b.y, b.r, "red"))
                elif b.aspect >= 1.5 and b.fill >= 0.45 and b.r < 2.3 * R_BULLET_MAX * k:
                    things.extend(_split_pair(b))  # two bullets touching
            elif b.r > R_BOSS_MIN * k:
                if b.aspect <= 1.6:  # (the boss's long health bar at the bottom is red too)
                    things.append(Thing("boss", b.x, b.y, b.r))
            elif b.aspect >= 1.6 and b.r < 2.3 * R_BULLET_MAX * k and b.fill >= 0.45:
                things.extend(_split_pair(b))
            else:
                things.append(Thing("grunt", b.x, b.y, b.r))

        balls = [b for b in bl["orange"] if id(b) not in text and R_BULLET_MIN * k <= b.r < R_BULLET_MAX * k * 1.3]
        rings = find_rings(bgr, COLORS["orange"][0], [(b.x, b.y) for b in balls], 10.0 * k) if balls else []
        for b in balls:
            ring = max((g for g in rings if g[2] > b.r * 1.6 and math.hypot(g[0] - b.x, g[1] - b.y) < g[2] * 0.75),
                       key=lambda g: g[2], default=None)
            if ring is not None:
                things.append(Thing("shooter", ring[0], ring[1], ring[2]))
            elif b.round_ball():
                things.append(Thing("bullet", b.x, b.y, b.r, "orange"))

        for b in bl["yellow"]:
            if id(b) in text or b.r < R_BULLET_MIN * k:
                continue
            if b.r < R_BULLET_MAX * k:
                if b.round_ball():
                    things.append(Thing("bullet", b.x, b.y, b.r, "yellow"))
                continue
            rr = find_rings(bgr, COLORS["yellow"][0], [(b.x, b.y)], 10.0 * k)
            ring = max((g for g in rr if g[2] > b.r * 1.1 and math.hypot(g[0] - b.x, g[1] - b.y) < g[2] * 0.75),
                       key=lambda g: g[2], default=None)
            things.append(Thing("yellow", b.x, b.y, ring[2] if ring else b.r * 1.35))

        for b in bl["tank"]:
            if b.r >= 30 * k:
                things.append(Thing("tank", b.x, b.y, b.r))
        for b in bl["tiny"]:
            if id(b) not in text and b.r >= 12 * k:
                things.append(Thing("tiny", b.x, b.y, b.r))
        for b in bl["health"]:
            if id(b) not in text and 4 * k <= b.r <= 18 * k and b.aspect <= 1.4:
                things.append(Thing("health", b.x, b.y, b.r))
        # the ring and the square in the middle of a health circle are one pickup
        hp = [t for t in things if t.kind == "health"]
        for t in hp:
            if any(o is not t and o.r > t.r and math.hypot(o.x - t.x, o.y - t.y) < o.r for o in hp):
                things.remove(t)

        things += find_spawn_rings(bgr, things)
        player = find_player(bl, k, things)
        # enemies flash white when hit: a white shape without your gray ball next to it is one of them
        for b in bl["white"]:
            if b.r < 20 * k:
                continue
            if b.r <= R_SAUCER[1] * k and any(math.hypot(g.x - b.x, g.y - b.y) < b.r + g.r * 1.5 for g in bl["gray"]):
                continue  # your saucer (your gray ball is next to it)
            if player and math.hypot(player[0] - b.x, player[1] - b.y) < 2.5 * player[2]:
                continue
            if b.r > R_BOSS_MIN * k:
                if b.aspect <= 1.6:
                    things.append(Thing("boss", b.x, b.y, b.r))
            elif b.solid >= 0.7:
                things.append(Thing("grunt", b.x, b.y, b.r))
        # the same thing found twice (e.g. a ring and the shape inside it): keep one
        out = []
        for t in sorted(things, key=lambda t: -t.r):
            if not any(o.kind == t.kind and math.hypot(o.x - t.x, o.y - t.y) < 0.5 * o.r for o in out):
                out.append(t)
        return player, out


def _split_pair(b):
    """A long blob made of two touching bullets -> two bullets at its ends."""
    r = min(b.w, b.h) / 2.0
    if b.w >= b.h:
        return [Thing("bullet", b.bx + r, b.y, r, "red"), Thing("bullet", b.bx + b.w - r, b.y, r, "red")]
    return [Thing("bullet", b.x, b.by + r, r, "red"), Thing("bullet", b.x, b.by + b.h - r, r, "red")]


def _text_pieces(bl, k):
    """ids of blobs that are letters of floating score text ("+10", "+25"...): 2+ small pieces of the
    same color side by side in a row, at least one of them not ball-shaped."""
    out = set()
    for name in ("red", "orange", "yellow", "tiny", "health"):
        # letters are small: anything as big as a tiny tank (r ~22) or a grunt is never text
        pieces = [b for b in bl[name] if b.r < R_TEXT_MAX * k]
        pieces.sort(key=lambda b: b.bx)
        for i, a in enumerate(pieces):
            row = [a]
            for c in pieces[i + 1:]:
                hmax = max(a.h, c.h)
                if c.bx - (row[-1].bx + row[-1].w) > 0.8 * hmax:
                    break
                if abs(a.by - c.by) <= 0.3 * hmax and abs(a.h - c.h) <= 0.35 * hmax:
                    row.append(c)
            if len(row) >= 2 and not all(p.round_ball() for p in row):
                out.update(id(p) for p in row)
    return out


def find_player(bl, k, things):
    """The player: the white UFO saucer with the gray ball next to it. Position = the gray ball (the
    aim line starts there). Falls back to just the saucer, or just a round gray ball (plain look)."""
    saucers = [b for b in bl["white"] if R_SAUCER[0] * k <= b.r <= R_SAUCER[1] * k and b.solid >= 0.55
               and any(math.hypot(g.x - b.x, g.y - b.y) < b.r + 2.5 * g.r for g in bl["gray"])]
    balls = [b for b in bl["gray"] if R_PLAYER_BALL[0] * k <= b.r <= R_PLAYER_BALL[1] * k and b.aspect <= 1.5]
    bosses = [t for t in things if t.kind == "boss"]

    def inside_boss(x, y):
        return any(math.hypot(x - t.x, y - t.y) < 0.5 * t.r for t in bosses)

    best = None
    for s in saucers:
        ball = min(balls, key=lambda b: math.hypot(b.x - s.x, b.y - s.y), default=None)
        if ball is not None and math.hypot(ball.x - s.x, ball.y - s.y) < 2.5 * ball.r + 0.5 * s.r:
            cand = (0, ball.x, ball.y, HIT_FACTOR * ball.r)
        else:
            cand = (1, s.x, s.y, HIT_FACTOR * 19.0 * k)
        if not inside_boss(cand[1], cand[2]) and (best is None or cand[0] < best[0]):
            best = cand
    if best is None:
        for b in balls:
            if b.round_ball() and not inside_boss(b.x, b.y):
                best = (2, b.x, b.y, HIT_FACTOR * b.r)
                break
    return None if best is None else best[1:]


# --------------------------------------------------------------------------- spawn warnings
def find_spawn_rings(bgr, things):
    """The thin colored warning rings the game draws where an enemy is about to appear: [Thing("spawn")].
    Big (r > 5% of the height), thin, round (or cut off by the edge), and nothing inside yet."""
    H, W = bgr.shape[:2]
    s = 4
    small = cv2.resize(bgr, (W // s, H // s), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hue = hsv[..., 0]
    mask = ((hsv[..., 1] > 90) & (hsv[..., 2] > 45) & ~((hue > 80) & (hue < 100))).astype(np.uint8)
    n, _, st, cc = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        x0, y0, w, h, area = (int(v) for v in st[i])
        r = max(w, h) / 2.0 * s
        if r < 0.05 * H or r > 0.25 * H or area > 0.22 * w * h:
            continue
        edge = x0 <= 1 or y0 <= 1 or x0 + w >= small.shape[1] - 1 or y0 + h >= small.shape[0] - 1
        if not edge and not (0.7 <= w / h <= 1.4):
            continue
        cx, cy = (x0 + w / 2.0) * s, (y0 + h / 2.0) * s
        if edge:  # cut off by the edge: the center is where the full circle's would be
            if x0 <= 1:
                cx = (x0 + w) * s - r
            elif x0 + w >= small.shape[1] - 1:
                cx = x0 * s + r
            if y0 <= 1:
                cy = (y0 + h) * s - r
            elif y0 + h >= small.shape[0] - 1:
                cy = y0 * s + r
        if any(math.hypot(t.x - cx, t.y - cy) < 0.6 * r for t in things if t.kind != "bullet"):
            continue  # something is already there (a shooter's or yellow mob's own ring)
        out.append(Thing("spawn", cx, cy, r))
    return out


# --------------------------------------------------------------------------- rings (shooter, yellow)
def _ring_with_inside(mask, center, r):
    """A ring with something glued inside (the yellow square): lit at the outer edge, dark just inside."""
    cx, cy = center
    h, w = mask.shape
    ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)

    def lit(rr):
        xs = np.clip(np.round(cx + rr * np.cos(ang)).astype(int), 0, w - 1)
        ys = np.clip(np.round(cy + rr * np.sin(ang)).astype(int), 0, h - 1)
        return float((mask[ys, xs] > 0).mean())
    return max(lit(r - 1.0), lit(r - 1.5), lit(r - 2.0)) >= 0.7 and min(lit(r * 0.78), lit(r * 0.82)) <= 0.4


def find_rings(bgr, lab, centers, ball_r):
    """Thin rings of this color's hue around the given points: [(x, y, r)] in frame pixels."""
    out = []
    H, W = bgr.shape[:2]
    ref = cv2.cvtColor(cv2.cvtColor(np.uint8([[lab]]), cv2.COLOR_LAB2BGR), cv2.COLOR_BGR2HSV)[0, 0]
    hue = int(ref[0])
    for (x, y) in centers:
        half = int(ball_r * 6)
        x0, y0 = max(0, int(x) - half), max(0, int(y) - half)
        crop = bgr[y0:min(H, int(y) + half), x0:min(W, int(x) + half)]
        if crop.shape[0] < 8 or crop.shape[1] < 8:
            continue
        small = cv2.resize(crop, (crop.shape[1] // 2, crop.shape[0] // 2), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        raw = cv2.inRange(hsv, np.array([max(hue - 6, 0), 90, 45], np.uint8), np.array([min(hue + 6, 179), 255, 255], np.uint8))
        mask = cv2.dilate(raw, np.ones((3, 3), np.uint8))
        n, _, st, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for i in range(1, n):
            bw, bh, area = st[i, 2], st[i, 3], st[i, 4]
            r = max(bw, bh)  # = radius in crop pixels (half-size crop x2 / 2)
            if r < ball_r * 1.6 or r > ball_r * 8 or max(bw, bh) > 1.4 * min(bw, bh):
                continue
            if area > 0.6 * bw * bh and not _ring_with_inside(raw, cents[i], max(bw, bh) / 2.0):
                continue
            g = (x0 + cents[i][0] * 2 + 1, y0 + cents[i][1] * 2 + 1, float(r))
            if not any(abs(g[0] - o[0]) < 6 and abs(g[1] - o[1]) < 6 for o in out):
                out.append(g)
    return out


# --------------------------------------------------------------------------- GAME OVER screen
def hit_flash(bgr):
    """The whole screen flashes red for a moment when you get hit (also while it fades out). An enemy
    behind a HUD panel can't fake this, unlike reading the HP bar."""
    sm = bgr[::16, ::16].astype(np.int16)
    b, g, r = (float(np.median(sm[..., i])) for i in range(3))
    return r >= 18 and r > 2 * b and r - max(b, g) >= 10


def hud_visible(bgr):
    """The game's HP panel (dark red bar at the top left) is on screen: you're in an arcade game."""
    H, W = bgr.shape[:2]
    reg = bgr[int(0.015 * H):int(0.15 * H), int(0.005 * W):int(0.30 * W)].astype(np.int16)
    b, g, r = reg[..., 0], reg[..., 1], reg[..., 2]
    red = (r > 32) & (r < 110) & (r > b + 15) & (r > g + 15)
    return int((red.mean(1) >= 0.2).sum()) >= 0.02 * H


def game_over_info(bgr):
    """Median BGR of the screen edges and of the middle, and whether that's the GAME OVER screen
    (dark red background with a dark gray panel in the middle)."""
    h, w = bgr.shape[:2]
    step = max(1, min(h, w) // 90)
    bh, bw = h // 9, w // 13
    border = np.concatenate([bgr[:bh:step, ::step, :3].reshape(-1, 3), bgr[h - bh::step, ::step, :3].reshape(-1, 3),
                             bgr[::step, :bw:step, :3].reshape(-1, 3), bgr[::step, w - bw::step, :3].reshape(-1, 3)])
    b, g, r = np.median(border, axis=0)
    cb, cg, cr = np.median(bgr[int(h * .28):int(h * .78):step, int(w * .34):int(w * .66):step, :3].reshape(-1, 3), axis=0)
    red_bg = r >= 25 and r - max(b, g) >= 15
    panel = 12 <= max(cb, cg, cr) <= 70 and max(cb, cg, cr) - min(cb, cg, cr) <= 14
    return {"border": (int(b), int(g), int(r)), "middle": (int(cb), int(cg), int(cr)), "game_over": bool(red_bg and panel)}


def is_game_over(bgr):
    return game_over_info(bgr)["game_over"]


def find_play_again(bgr, which="left"):
    """Center (x, y) of a button on the GAME OVER screen, or None: the dark panel in the middle, then
    the left (PLAY AGAIN) or right (LEAVE) of the two lighter buttons at its bottom (or where it sits
    on the panel)."""
    h, w = bgr.shape[:2]
    s = 4
    small = cv2.resize(bgr, (w // s, h // s), interpolation=cv2.INTER_AREA).astype(np.int16)
    mx, mn = small.max(axis=2), small.min(axis=2)
    neutral = ((mx - mn) <= 14) & (mx >= 12) & (mx <= 95)
    mask = cv2.morphologyEx(neutral.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    px, py, pw, ph, area = (int(v) for v in stats[i])
    if area < 0.08 * mask.size or not (px < small.shape[1] / 2 < px + pw):
        return None
    panel = np.median(mx[py:py + ph, px:px + pw][neutral[py:py + ph, px:px + pw]])
    y0 = py + int(ph * 0.65)
    reg = mx[y0:py + ph, px:px + pw]
    lighter = (reg >= panel + 7) & (reg <= panel + 70) & neutral[y0:py + ph, px:px + pw]
    lighter = cv2.morphologyEx(lighter.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m, _l, bs, bc = cv2.connectedComponentsWithStats(lighter, connectivity=8)
    buttons = [(bc[j][0], bc[j][1]) for j in range(1, m)
               if bs[j, cv2.CC_STAT_WIDTH] > 0.2 * pw and bs[j, cv2.CC_STAT_HEIGHT] > 0.04 * ph]
    if len(buttons) >= 2 or (buttons and which == "left"):
        bx, by = min(buttons) if which == "left" else max(buttons)
        return ((px + bx) * s + s / 2, (y0 + by) * s + s / 2)
    return ((px + (0.279 if which == "left" else 0.72) * pw) * s, (py + 0.880 * ph) * s)


def find_leave(bgr):
    return find_play_again(bgr, "right")


# --------------------------------------------------------------------------- pictures for debugging
DRAW = {"spawn": (255, 0, 255), "bullet": (80, 80, 255), "grunt": (60, 60, 230), "shooter": (50, 150, 255), "yellow": (90, 220, 230),
        "tank": (230, 90, 200), "tiny": (240, 160, 240), "boss": (0, 0, 255), "health": (120, 230, 120)}


def annotate(frame, player, things, keys=(), aim=None, text=""):
    img = frame.copy()
    for t in things:
        c = DRAW.get(t.kind, (255, 255, 255))
        cv2.circle(img, (int(t.x), int(t.y)), int(t.r) + 3, c, 2)
        if t.kind != "bullet":
            cv2.putText(img, t.kind, (int(t.x - t.r), int(t.y - t.r - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)
    if player:
        x, y, r = player
        cv2.circle(img, (int(x), int(y)), int(r), (255, 255, 255), 2)
        cv2.putText(img, "YOU", (int(x - 14), int(y + r + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if aim:
            cv2.line(img, (int(x), int(y)), (int(aim[0]), int(aim[1])), (0, 255, 255), 1)
    cv2.rectangle(img, (0, 0), (img.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(img, f"keys {''.join(k[0].upper() for k in keys) or '-'}  {text}", (8, 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 255, 140), 1, cv2.LINE_AA)
    return img
