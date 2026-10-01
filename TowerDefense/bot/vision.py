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
    "player": "YOU (the gray ball or the white UFO)",
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

# Colors and sizes measured from real screenshots of the Roblox game (a 2534x1239 play area), last
# checked against close-ups of every enemy. Sizes are scaled to your play area's height when the preset
# is applied. Bump PRESET_VERSION when this changes: configs using the preset then pick it up by themselves.
PRESET_VERSION = 2
PRESET = {
    "ref_height": 1239,
    "colors": {
        "player": {"lab": [172, 128, 123], "radius": 26.5},
        "enemy_bullet": {"lab": [127, 189, 166], "radius": 14.5},     # the boss's red bullets
        "shooter_bullet": {"lab": [182, 155, 190], "radius": 12.5},   # orange bullets
        "grunt": {"lab": [138, 190, 165], "radius": 43.5},            # red square
        "shooter": {"lab": [184, 155, 190], "radius": 35.0},          # orange ball: its whole ring
        "tank": {"lab": [149, 189, 66], "radius": 70.0},              # purple hollow square (63-80 as it turns)
        "tank_mini": {"lab": [180, 170, 86], "radius": 32.0},         # light purple tiny tank
        "boss": {"lab": [130, 191, 167], "radius": 162.0},            # red cross
        "health": {"lab": [217, 64, 174], "radius": 9.0},
        "runner": {"lab": [225, 123, 198], "radius": 32.0},           # yellow square (inside a ring, r ~43)
        "yellow_bullet": {"lab": [220, 123, 196], "radius": 12.8},
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


# The see-through panels the player can move behind: the health bar (dark red) and the score
# panel (dark gray), as BGR colors. Behind them the player's gray gets blended with these.
HUD_PANELS_BGR = [(20, 18, 16), (22, 18, 48)]
PANEL_STRENGTHS = [0.3, 0.5, 0.7]


def shaded_player_colors(lab):
    """The player's color as it looks behind each HUD panel, at a few see-through strengths."""
    bgr = cv2.cvtColor(np.uint8([[lab]]), cv2.COLOR_LAB2BGR)[0, 0].astype(np.float64)
    out = []
    for panel in HUD_PANELS_BGR:
        for a in PANEL_STRENGTHS:
            mix = np.clip(bgr * (1 - a) + np.array(panel) * a, 0, 255).astype(np.uint8)
            out.append(bgr_to_lab_pixel(mix))
    return out


def solidity(sel, area):
    """How 'solid' a shape is: its area divided by the area of its convex outline. Balls and squares
    are ~0.9-1.0; floating text like "+10" (thin strokes with gaps and holes) is much lower."""
    if area < 12:
        return 1.0  # too small to judge
    contours, _ = cv2.findContours(sel.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 1.0
    hull = cv2.contourArea(cv2.convexHull(max(contours, key=cv2.contourArea)))
    return min(1.0, area / hull) if hull > 0 else 1.0


# Kinds that are always a filled ball/square/diamond; anything of their color that isn't solid is text.
SOLID_KINDS = {"player", "grunt", "runner", "shooter", "tank_mini", "enemy_bullet", "shooter_bullet", "yellow_bullet"}
MIN_SOLIDITY = 0.75


def text_rows(boxes):
    """Rows (lists of indexes) of boxes that look like letters/digits of one line of text: 2+ pieces of similar
    height, tops lined up, side by side with small gaps (e.g. the "1" and "0" of a "+10" popup)."""
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: boxes[i][0])
    for a_i, i in enumerate(order):
        xi, yi, wi, hi = boxes[i]
        for j in order[a_i + 1:]:
            xj, yj, wj, hj = boxes[j]
            hmax = max(hi, hj)
            if xj - (xi + wi) > 0.8 * hmax:
                break  # sorted by x: everything further right is too far away
            if abs(yi - yj) <= 0.25 * hmax and abs(hi - hj) <= 0.35 * hmax and xj >= xi + wi * 0.5:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) >= 2]


def find_rings_near(bgr, lab, balls, ball_r):
    """Rings around the given balls only (much cheaper than searching the whole screen)."""
    out = []
    h, w = bgr.shape[:2]
    for (x, y) in balls:
        half = int(ball_r * 5)
        x0, y0 = max(0, int(x) - half), max(0, int(y) - half)
        crop = bgr[y0:min(h, int(y) + half), x0:min(w, int(x) + half)]
        if crop.shape[0] < 8 or crop.shape[1] < 8:
            continue
        for (rx, ry, rr) in find_rings(crop, lab, 2, ball_r):
            g = (rx + x0, ry + y0, rr)
            if not any(abs(g[0] - o[0]) < 6 and abs(g[1] - o[1]) < 6 for o in out):
                out.append(g)
    return out


def _ring_with_inside(mask, center, r):
    """A ring with something inside that got glued to it (the yellow mob's square): lit all around at
    the outer edge, with a dark gap just inside. A filled ball is lit at both."""
    cx, cy = center
    h, w = mask.shape
    ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)

    def lit(rr):
        xs = np.clip(np.round(cx + rr * np.cos(ang)).astype(int), 0, w - 1)
        ys = np.clip(np.round(cy + rr * np.sin(ang)).astype(int), 0, h - 1)
        return float((mask[ys, xs] > 0).mean())
    outer = max(lit(r - 1.0), lit(r - 1.5), lit(r - 2.0))
    gap = min(lit(r * 0.78), lit(r * 0.82))
    return outer >= 0.7 and gap <= 0.4


def find_rings(bgr, lab, scale, ball_r):
    """Thin round rings in this color (the orange shooter's ring), as (x, y, r) in full-size pixels.
    The ring is ~1 pixel wide, so the image is shrunk by averaging (keeps a faint ring) and matched
    on hue only, then small gaps are closed."""
    small = cv2.resize(bgr, (bgr.shape[1] // scale, bgr.shape[0] // scale), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    ref = cv2.cvtColor(cv2.cvtColor(np.uint8([[lab]]), cv2.COLOR_LAB2BGR), cv2.COLOR_BGR2HSV)[0, 0]
    h = int(ref[0])
    raw = cv2.inRange(hsv, np.array([max(h - 6, 0), 90, 45], np.uint8), np.array([min(h + 6, 179), 255, 255], np.uint8))
    mask = cv2.dilate(raw, np.ones((3, 3), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        bw, bh, area = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT], stats[i, cv2.CC_STAT_AREA]
        r = max(bw, bh) / 2.0 * scale
        if r < ball_r * 1.6 or r > ball_r * 8 or max(bw, bh) > 1.4 * min(bw, bh):
            continue
        if area > 0.6 * bw * bh and not _ring_with_inside(raw, cents[i], max(bw, bh) / 2.0):
            continue  # a filled blob (e.g. a ball with the ring glued on), not a ring
        out.append((cents[i][0] * scale + scale / 2, cents[i][1] * scale + scale / 2, r))
    return out


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


# The player's looks: the gray ball (with a white shield), and the white "UFO" (a ball on an oval with
# black windows). The white look is matched on its own, so the gray ball's white shield doesn't merge
# into the ball.
PLAYER_GRAY = [172, 128, 123]
PLAYER_WHITE = [251, 128, 128]
FG_LEVEL = 45     # a pixel brighter than this in any channel is "something"; the background is ~(8, 5, 4)
SHADE_TOL = [16, 9, 9]
_BIN_LAB = None   # Lab color of every 64x64x64 BGR bin (built once)


def _close(a, b, tol):
    return all(abs(float(x) - float(y)) <= t for x, y, t in zip(a, b, tol))


def remember_player_look(cfg, look):
    """Keep `look` ({"lab", "radius"}) as an extra look of the player (no duplicates, at most 6)."""
    half = [t * 0.5 for t in cfg.get("tolerance", DEFAULT_TOLERANCE)]
    looks = cfg.setdefault("player_looks", [])
    if any(_close(lk["lab"], look["lab"], half) for lk in looks):
        return
    looks.append({"lab": [int(round(v)) for v in look["lab"]], "radius": round(float(look["radius"]), 1)})
    del looks[:-6]


def set_main_player(cfg, lab, radius):
    """Relearn the player: this is what it looks like now. The previous look is kept as an extra look,
    so both keep working (e.g. the gray ball and a skin)."""
    half = [t * 0.5 for t in cfg.get("tolerance", DEFAULT_TOLERANCE)]
    colors = cfg.setdefault("colors", {})
    old = colors.get("player")
    if old and old.get("lab") and old.get("radius") and not _close(old["lab"], lab, half):
        remember_player_look(cfg, old)
    cfg["player_looks"] = [lk for lk in cfg.get("player_looks", []) if not _close(lk["lab"], lab, half)]
    colors["player"] = {"lab": [int(round(v)) for v in lab], "radius": round(float(radius), 1)}


def game_over_info(bgr):
    """What the game-over check measures: median BGR of the screen edges and of the middle."""
    h, w = bgr.shape[:2]
    step = max(1, min(h, w) // 90)  # look at a sparse grid of pixels only: cheap enough for every frame
    bh, bw = h // 9, w // 13
    border = np.concatenate([bgr[:bh:step, ::step, :3].reshape(-1, 3), bgr[h - bh::step, ::step, :3].reshape(-1, 3),
                             bgr[::step, :bw:step, :3].reshape(-1, 3), bgr[::step, w - bw::step, :3].reshape(-1, 3)])
    b, g, r = np.median(border, axis=0)
    cb, cg, cr = np.median(bgr[int(h * .28):int(h * .78):step, int(w * .34):int(w * .66):step, :3].reshape(-1, 3), axis=0)
    red_bg = r >= 25 and r - max(b, g) >= 15
    panel = 12 <= max(cb, cg, cr) <= 70 and max(cb, cg, cr) - min(cb, cg, cr) <= 14
    return {"border": (int(b), int(g), int(r)), "middle": (int(cb), int(cg), int(cr)), "game_over": bool(red_bg and panel)}


def is_game_over(bgr):
    """The GAME OVER screen: the whole background turns dark red and a big dark gray panel (score, top
    scores, PLAY AGAIN) sits in the middle. A red hit flash or a big red boss doesn't look like that."""
    return game_over_info(bgr)["game_over"]


def find_play_again(bgr):
    """Center (x, y) of the PLAY AGAIN button on the GAME OVER screen, in frame pixels, or None.
    Finds the dark gray panel in the middle, then the left one of the two buttons at its bottom (a bit
    lighter gray than the panel). If the buttons can't be told apart, uses where PLAY AGAIN sits on the
    panel (measured from a real screenshot)."""
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
        return None  # no big panel in the middle
    panel = np.median(mx[py:py + ph, px:px + pw][neutral[py:py + ph, px:px + pw]])
    y0 = py + int(ph * 0.65)
    reg_mx = mx[y0:py + ph, px:px + pw]
    lighter = (reg_mx >= panel + 7) & (reg_mx <= panel + 70) & neutral[y0:py + ph, px:px + pw]
    lighter = cv2.morphologyEx(lighter.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m, _l, bs, bc = cv2.connectedComponentsWithStats(lighter, connectivity=8)
    buttons = [(bc[j][0], bc[j][1]) for j in range(1, m)
               if bs[j, cv2.CC_STAT_WIDTH] > 0.2 * pw and bs[j, cv2.CC_STAT_HEIGHT] > 0.04 * ph]
    if buttons:
        bx, by = min(buttons)  # the left one
        return ((px + bx) * s + s / 2, (y0 + by) * s + s / 2)
    return ((px + 0.279 * pw) * s, (py + 0.880 * ph) * s)


def _bin_lab():
    global _BIN_LAB
    if _BIN_LAB is None:
        v = (np.arange(64, dtype=np.int32) << 2) + 2
        b, g, r = np.meshgrid(v, v, v, indexing="ij")
        bgr = np.stack([b, g, r], -1).astype(np.uint8).reshape(512, 512, 3)
        _BIN_LAB = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.int16)
    return _BIN_LAB


def _roundish(blob):
    """A ball: about as wide as high, fills its box like a circle does, and solid."""
    bw, bh = blob[5][2], blob[5][3]
    return max(bw, bh) <= 1.2 * min(bw, bh) and blob[6] >= 0.6 and blob[4] >= MIN_SOLIDITY


class Detector:
    """Finds things by color, then by size.

    Lightweight: one quick pass over the (half-size) screen finds the spots where there is anything
    at all (the game is black), then only those small spots are looked at. Colors are looked up in a
    table built once (every possible color -> which kind of thing it belongs to), so a spot costs
    a few microseconds no matter how many kinds there are.

    In the Roblox game the basic mob, the boss and the boss's bullets are all the same red,
    so when several classes share a color each blob goes to the class whose normal size
    is closest (a small red circle is a bullet, a big red cross is the boss).
    """

    def __init__(self, cfg):
        self.scale = int(cfg.get("downscale", 2))
        self.tol = cfg.get("tolerance", DEFAULT_TOLERANCE)
        self.tol_arr = np.array(self.tol)
        self.ignore = cfg.get("ignore", [])  # things marked "not a thing" in the photo trainer
        # "Danger size": treat some kinds as bigger than they look so the bot keeps more distance.
        self.expand = {k: float(v) for k, v in cfg.get("expand", {}).items()}
        # Group classes whose colors are practically the same (calibration clicks on the same red
        # rarely give identical numbers), so one red blob is never reported as two things.
        self.groups = []  # [([lab, ...], [(name, radius), ...])]
        tol = np.array(self.tol)
        # Anything never calibrated uses the preset (an uncalibrated kind would be invisible).
        colors = dict(cfg.get("colors", {}))
        reg = cfg.get("region")
        scale = reg["height"] / PRESET["ref_height"] if reg and reg.get("height") else 1.0
        for name, p in PRESET["colors"].items():
            if not (colors.get(name) and colors[name].get("lab")):
                colors[name] = {"lab": list(p["lab"]), "radius": round(p["radius"] * scale, 1)}
        for name, c in colors.items():
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
        # Color table entries: (lab, tolerance, group id). Group ids start at 1 (0 = nothing).
        # Extra looks of the player you taught it ("Relearn the player" keeps the old look here).
        self.player_looks = [lk for lk in cfg.get("player_looks", []) if lk.get("lab") and lk.get("radius")]
        entries = []
        self.shade_gid = self.white_gid = None
        extra = len(self.groups)
        for gid, (labs, members) in enumerate(self.groups, 1):
            for lab in labs:
                entries.append((lab, self.tol, gid))
            if any(m[0] == "player" for m in members):
                looks = [PLAYER_GRAY] if not any(np.all(np.abs(np.array(PLAYER_GRAY) - np.array(o)) <= 4) for o in labs) else []
                entries += [(lab, self.tol, gid) for lab in looks]
                extra += 1
                self.white_gid = extra  # the other looks: the white UFO and any you taught it
                entries.append((PLAYER_WHITE, [12, 6, 6], self.white_gid))
                other_looks = [lk["lab"] for lk in self.player_looks
                               if not any(np.all(np.abs(np.array(lk["lab"]) - np.array(o)) <= 4) for o in labs)]
                entries += [(lab, self.tol, self.white_gid) for lab in other_looks]
                if len(members) == 1:
                    # The player behind the see-through health bar / score panel: its own group, only
                    # used when the player isn't found normally.
                    extra += 1
                    self.shade_gid = extra
                    for base in list(labs) + looks + [PLAYER_WHITE] + other_looks:
                        entries += [(sh, SHADE_TOL, self.shade_gid) for sh in shaded_player_colors(base)]
        self.lut = self._build_lut(entries)
        self.player_gid = next((gid for gid, (_l, mem) in enumerate(self.groups, 1) if any(m[0] == "player" for m in mem)), None)
        pr = next((m[1] for _l, mem in self.groups for m in mem if m[0] == "player"), 0.0)
        radii = [pr] + [float(lk["radius"]) for lk in self.player_looks] if pr else [0.0]
        self.player_r_range = (0.65 * min(radii), 1.6 * max(radii))  # any of its looks
        self.player_min_side = 2 * self.player_r_range[0]  # full-size pixels
        # Floating text letters are at most about bullet-sized.
        bullet_r = [m[1] for _l, mem in self.groups for m in mem if m[0] in BULLET_CLASSES]
        self.text_max_r = 1.5 * (min(bullet_r) if bullet_r else 14.0)
        self.min_r = min((m[1] for _, members in self.groups for m in members), default=5.0)

    @staticmethod
    def _build_lut(entries):
        """Every possible color (64 levels per channel) -> the closest matching group id, or 0."""
        bins = _bin_lab()
        best = np.full(len(bins), np.inf, np.float32)
        lut = np.zeros(len(bins), np.uint8)
        for lab, tol, gid in entries:
            d = (np.abs(bins - np.array(lab, np.int16)) / np.array(tol, np.float32)).max(axis=1)
            take = (d <= 1.0) & (d < best)
            best[take] = d[take]
            lut[take] = gid
        return lut

    def _ignored(self, lab, r):
        """True if this looks like something you marked as 'not a thing' in the photo trainer."""
        for ig in self.ignore:
            if np.all(np.abs(lab - np.array(ig["lab"])) <= self.tol_arr * 0.5) and 0.75 <= r / ig["radius"] <= 1.33:
                return True
        return False

    def _blobs(self, bgr):
        """{group id: [(x, y, r, mean_lab, solidity, box), ...]} in downscaled pixels."""
        s = self.scale
        small = cv2.resize(bgr, (bgr.shape[1] // s, bgr.shape[0] // s), interpolation=cv2.INTER_NEAREST) if s > 1 else bgr
        b, g, r = cv2.split(small)
        _, fg = cv2.threshold(cv2.max(cv2.max(b, g), r), FG_LEVEL, 1, cv2.THRESH_BINARY)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
        H, W = fg.shape
        wide = np.maximum(stats[:, 2], stats[:, 3])
        min_side = max(2, int(self.min_r * 0.9 / s))
        # (No upper limit here: the aim line can connect you to half the screen.)
        spots = np.nonzero(wide >= min_side)[0]
        too_big = 0.35 * min(H, W)
        # Small spots can only be bullets or health pickups; most small spots are letters of the chat
        # and HUD text. Look at the middle pixel first and skip them when it's nothing or player-gray.
        player_ish = {self.player_gid, self.white_gid, self.shade_gid} - {None}
        player_min = self.player_min_side / s
        lut = self.lut
        out = {}
        for i in spots:
            if i == 0:
                continue
            x0, y0, w, h = (int(v) for v in stats[i, :4])
            if max(w, h) < player_min:
                c = small[y0 + h // 2, x0 + w // 2]
                mid = lut[((int(c[0]) >> 2) << 12) | ((int(c[1]) >> 2) << 6) | (int(c[2]) >> 2)]
                if mid == 0 or mid in player_ish:
                    continue
            crop = small[y0:y0 + h, x0:x0 + w].astype(np.int32)
            grp = self.lut[((crop[..., 0] >> 2) << 12) | ((crop[..., 1] >> 2) << 6) | (crop[..., 2] >> 2)]
            grp[labels[y0:y0 + h, x0:x0 + w] != i] = 0  # only this spot (neighbors are their own spots)
            present = np.unique(grp)
            if present[-1] == 0:
                continue
            lab_crop = None
            for gid in present:
                if gid == 0:
                    continue
                mask = (grp == gid).astype(np.uint8)
                m, cl, cs, cc = cv2.connectedComponentsWithStats(mask, connectivity=8)
                for j in range(1, m):
                    bx, by, bw, bh, area = (int(v) for v in cs[j])
                    if max(bw, bh) < min_side or max(bw, bh) > too_big:
                        continue  # a speck, or screen-sized: a color that matches the background
                    # Skip thin lines (the aim line) and text-like shapes: real things fill their box.
                    fill = 0.08 if gid in self.hollow_ok else 0.3
                    if max(bw, bh) > 3 * max(1, min(bw, bh)) or area < fill * bw * bh:
                        continue
                    sel = cl[by:by + bh, bx:bx + bw] == j
                    if lab_crop is None:
                        lab_crop = cv2.cvtColor(small[y0:y0 + h, x0:x0 + w], cv2.COLOR_BGR2LAB)
                    mean_lab = lab_crop[by:by + bh, bx:bx + bw][sel].mean(axis=0)
                    rr = max(bw, bh) / 2.0
                    solid = solidity(sel, area) if rr * s <= 60 else 1.0
                    out.setdefault(int(gid), []).append((x0 + cc[j][0], y0 + cc[j][1], rr, mean_lab, solid,
                                                         (x0 + bx, y0 + by, bw, bh), area / float(bw * bh)))
        return out

    @property
    def hollow_ok(self):
        # Health pickups may be drawn as a ring, so allow hollow shapes for them.
        if not hasattr(self, "_hollow"):
            self._hollow = {gid for gid, (_l, members) in enumerate(self.groups, 1)
                            if any(m[0] == "health" for m in members)}
        return self._hollow

    def detect_detailed(self, bgr, keep_ignored=False):
        """Every detection as a dict: name (what the bot treats it as), cls (the calibrated class),
        x, y, r (full-size pixels) and lab (its average color). With keep_ignored, things on the
        ignore list are included too, marked "ignored": True (the photo trainer shows them)."""
        s = self.scale
        all_blobs = self._blobs(bgr)
        found = []
        for gid, (labs, members) in enumerate(self.groups, 1):
            blobs = all_blobs.get(gid, [])
            smallest = min(m[1] for m in members)
            names = {m[0] for m in members}
            player_r = dict(members).get("player")
            if player_r:
                # The white look (solid enough: the gray ball's thin white shield doesn't count).
                blobs = blobs + [b for b in all_blobs.get(self.white_gid, []) if b[4] >= 0.7]
                if self.shade_gid and all_blobs.get(self.shade_gid) and not any(
                        self.player_r_range[0] <= b[2] * s <= self.player_r_range[1] for b in blobs):
                    # the player behind a HUD panel (too dark = the boss's dark middle or a HUD box)
                    # and round (HUD boxes like the "P" key are this dark gray too, but wide).
                    blobs = blobs + [b for b in all_blobs[self.shade_gid]
                                     if b[3][0] >= 60 and max(b[5][2], b[5][3]) <= 1.4 * min(b[5][2], b[5][3])]
            if not blobs:
                continue
            # Orange shooters are a ball inside a ring; orange bullets are the same ball without one.
            rings = None
            if "shooter" in names:
                balls = [(b[0] * s + s / 2, b[1] * s + s / 2) for b in blobs if b[2] * s < smallest * 2.5]
                rings = find_rings_near(bgr, labs[0], balls, smallest)
            # The yellow mob is a square inside a ring too: its danger size is the ring.
            yellow_rings = None
            if "runner" in names:
                runner_r = dict(members)["runner"]
                centers = [(b[0] * s + s / 2, b[1] * s + s / 2) for b in blobs if b[2] * s >= 0.6 * runner_r]
                yellow_rings = find_rings_near(bgr, labs[0], centers, smallest) if centers else []
            used_rings = set()
            # Floating text ("+10", "+25"...) in a mob's color: a row of bullet-sized pieces where at
            # least one isn't a round ball (a "1", a "+", a "2"...). Rows of bullets and the 3 tiny tanks
            # of a dead tank (bigger than bullets) are kept.
            rows = text_rows([bl[5] for bl in blobs])
            if rows:
                text = set()
                for row in rows:
                    pieces = [k for k in row if blobs[k][2] * s <= self.text_max_r]
                    if len(pieces) >= 2 and not all(_roundish(blobs[k]) for k in pieces):
                        text.update(pieces)
                blobs = [bl for k, bl in enumerate(blobs) if k not in text]
            for (x, y, r, lab, solid, box, fill) in blobs:
                x, y, r = x * s + s / 2, y * s + s / 2, r * s
                # Pick the class with the closest normal size (compared as a ratio).
                cls, r_exp = min(members, key=lambda m: abs(math.log(max(r, 0.5) / m[1])))
                if r < smallest * 0.45:
                    continue  # specks and explosion particles
                # Two bullets touching look like one long blob that's about the size of a mob: still bullets.
                b_r = min((m[1] for m in members if m[0] in BULLET_CLASSES), default=None)
                if (b_r and cls not in BULLET_CLASSES and cls != "player" and r <= 2.3 * b_r
                        and max(box[2], box[3]) >= 1.5 * min(box[2], box[3])):
                    cls, r_exp = next(m for m in members if m[0] in BULLET_CLASSES and m[1] == b_r)
                if cls in BULLET_CLASSES and r > r_exp * 2.4:
                    continue
                if cls == "player" and not (self.player_r_range[0] <= r <= self.player_r_range[1]):
                    continue  # HUD text is gray too, but much smaller than the player
                if cls in BULLET_CLASSES and fill < 0.45:
                    continue  # bullets are balls; a lone "+" of a score popup fills only a third of its box
                if cls in SOLID_KINDS and cls != "player" and solid < MIN_SOLIDITY and r <= 35:
                    continue  # floating text ("+10" etc.) in a mob's color: not solid like the real thing
                              # (only small things: a big mob can look dented when another overlaps it)
                if rings is not None and cls in ("shooter", "shooter_bullet"):
                    ring = max((g for g in rings if g[2] > r * 1.5 and math.hypot(g[0] - x, g[1] - y) < g[2] * 0.7),
                               key=lambda g: g[2], default=None)  # the outer one is the real ring
                    if ring is not None:
                        cls, r = "shooter", ring[2]  # danger size = the whole ring, not just the ball
                        used_rings.add(ring)
                    elif "shooter_bullet" in names and r < 2.5 * dict(members).get("shooter_bullet", r):
                        cls = "shooter_bullet"
                if cls == "runner" and yellow_rings:
                    ring = max((g for g in yellow_rings if g[2] > r * 1.1 and math.hypot(g[0] - x, g[1] - y) < g[2] * 0.7),
                               key=lambda g: g[2], default=None)
                    if ring is not None:
                        r = ring[2]
                # Never ignore the player: a "not a thing" on it once would blind the bot for good.
                ignored = bool(self.ignore) and cls != "player" and self._ignored(lab, r)
                if ignored and not keep_ignored:
                    continue
                name = "enemy_bullet" if cls in BULLET_CLASSES else cls  # all bullets are dodged the same way
                found.append({"name": name, "cls": cls, "x": x, "y": y, "r": r, "lab": [float(v) for v in lab],
                              "ignored": ignored})
            # A shooter's ring with no ball visible (ball flashing or hidden) is still a shooter.
            # The boss's small orange rings are too small to count.
            for g in rings or []:
                if any(math.hypot(g[0] - u[0], g[1] - u[1]) < max(g[2], u[2]) for u in used_rings):
                    continue  # the same ring found twice (its inner and outer edge)
                if g not in used_rings and g[2] >= 2.2 * smallest:
                    found.append({"name": "shooter", "cls": "shooter", "x": g[0], "y": g[1], "r": g[2],
                                  "lab": [float(v) for v in labs[0]], "ignored": False})
        # The boss has a white square in its middle: nothing deep inside the boss is the player.
        bosses = [d for d in found if d["cls"] == "boss"]
        if bosses:
            found = [d for d in found if d["cls"] != "player" or
                     not any(math.hypot(d["x"] - b["x"], d["y"] - b["y"]) < 0.45 * b["r"] for b in bosses)]
        return found

    def detect(self, bgr):
        """Returns {class name: [(x, y, radius), ...]} in full-size pixel coordinates."""
        out = {name: [] for name in CLASSES}
        for d in self.detect_detailed(bgr):
            r = d["r"] if d["cls"] in ("player", "health") else d["r"] * self.expand.get(d["cls"], 1.0)
            out[d["name"]].append((d["x"], d["y"], r))
        return out


class Track:
    __slots__ = ("x", "y", "vx", "vy", "r", "kind", "age", "missing", "vmax")

    def __init__(self, x, y, r, kind, vx=0.0, vy=0.0):
        self.x, self.y, self.r, self.kind = x, y, r, kind
        self.vx, self.vy = vx, vy
        self.age = 0
        self.missing = 0
        self.vmax = 0.0  # fastest it has recently moved (e.g. the boss's rush), fades slowly


class Tracker:
    """Matches this frame's blobs to last frame's so every mob/bullet gets a velocity."""

    def __init__(self):
        self.tracks = []

    def update(self, dets, dt, player_xy, max_speed, new_bullet_speed):
        px, py = player_xy
        new_tracks = []
        bosses = []
        for kind in MOB_KINDS + ["enemy_bullet", "health"]:
            old = [t for t in self.tracks if t.kind == kind]
            det = dets.get(kind, [])
            # Match closest pairs first (not in detection order), so dense bullet rings don't get
            # their tracks swapped, which would give them wrong speeds.
            pairs = []
            for j, (x, y, r) in enumerate(det):
                limit = max_speed * dt + r + 6
                for i, t in enumerate(old):
                    d = math.hypot(t.x + t.vx * dt - x, t.y + t.vy * dt - y)
                    if d < limit:
                        pairs.append((d, i, j))
            pairs.sort()
            used, matched = set(), {}
            for d, i, j in pairs:
                if i not in used and j not in matched:
                    used.add(i)
                    matched[j] = i
            for j, (x, y, r) in enumerate(det):
                if j in matched:
                    t = old[matched[j]]
                    if dt > 0:
                        mvx, mvy = (x - t.x) / dt, (y - t.y) / dt
                        a = 1.0 if t.age == 0 else 0.5  # first real measurement replaces the guess
                        t.vx = (1 - a) * t.vx + a * mvx
                        t.vy = (1 - a) * t.vy + a * mvy
                    t.x, t.y, t.r = x, y, r
                    t.vmax = max(math.hypot(t.vx, t.vy), t.vmax * 0.995)
                    t.age += 1
                    t.missing = 0
                    new_tracks.append(t)
                else:
                    vx = vy = 0.0
                    if kind == "enemy_bullet":  # health pickups stay put
                        # A new bullet right next to the boss flies outward from it (its bullet rings);
                        # otherwise assume it's flying at the player.
                        boss = next((b for b in bosses if math.hypot(b.x - x, b.y - y) < b.r * 3), None)
                        ox, oy = (x - boss.x, y - boss.y) if boss else (px - x, py - y)
                        d = math.hypot(ox, oy) or 1.0
                        vx, vy = ox / d * new_bullet_speed, oy / d * new_bullet_speed
                    new_tracks.append(Track(x, y, r, kind, vx, vy))
            if kind == "boss":
                bosses = [t for t in new_tracks if t.kind == "boss"]
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

