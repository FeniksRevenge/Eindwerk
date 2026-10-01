"""
Deciding: where to move (which of the 8 directions, or stand still) and where to aim.

It tries 81 short plans: a first move (0.25 s) in each of 9 directions, each followed by a second move
(0.5 s) in each of 9 directions, and predicts for every plan where everything will be:
  - bullets fly in straight lines (their measured speed);
  - grunts, tiny tanks, tanks, yellow mobs and the boss walk toward where you will be;
  - orange shooters keep doing what they're doing (they keep their distance).
A plan that gets hit is out (the sooner the hit, the worse). Among the rest it prefers plans that keep
the most room to everything, end up away from walls and corners, away from crowds, near the middle, and
that pick up a green health circle on the way.

All distances are in screen pixels, scaled by your size (R) and speeds by your speed (V).
"""

import math

import numpy as np

S = math.sqrt(0.5)
DIRS = np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [S, S], [S, -S], [-S, S], [-S, -S]], dtype=float)
KEYS = [(), ("right",), ("left",), ("down",), ("up",), ("down", "right"), ("up", "right"), ("down", "left"),
        ("up", "left")]
DT = 0.05
LEG1, LEG2 = 5, 10                     # steps of DT: 0.25 s, then 0.5 s

# How fast each kind can walk, as a fraction of your speed (used until it's been measured), and
# whether it walks at you.
MOB_SPEED = {"grunt": 0.88, "tiny": 1.0, "tank": 0.5, "yellow": 0.6, "boss": 0.6, "shooter": 0.7}
CHASERS = {"grunt", "tiny", "tank", "yellow", "boss"}
BOSS_KEEP = 0.33    # distance to keep from the boss, as a fraction of the arena's height
# Room to keep (x R) and how much to dislike being near each kind.
MARGIN = {"grunt": 1.3, "tiny": 1.3, "tank": 3.0, "yellow": 1.6, "shooter": 1.3, "boss": 6.0}
CROWD = {"grunt": 1.0, "tiny": 1.2, "tank": 1.2, "yellow": 2.0, "shooter": 1.3, "boss": 3.0}
# Which mob to shoot first (bigger = sooner): yellow mobs, then orange shooters.
SPAWN_PRIORITY = 1.1   # prefire at warning rings: before tanks/boss, after things already closing in
AIM_PRIORITY = {"yellow": 3.0, "shooter": 2.0, "tiny": 1.4, "grunt": 1.3, "tank": 1.0, "boss": 1.0}

# Your body: the gray ball plus the white saucer, which sits on the side away from the mouse (the UFO
# turns to face where you aim). As an oval around the ball, in R: centered BODY_BACK behind the ball,
# BODY_LONG long along the aim line, BODY_WIDE across it (measured on recordings).
BODY_BACK, BODY_LONG, BODY_WIDE = 0.35, 1.0, 1.55



def body_reach(v, face, R):
    """Your body's reach (px) from the oval's center in the direction of the vectors v (..., 2);
    face = unit vector toward the mouse."""
    n = np.sqrt((v ** 2).sum(-1)) + 1e-9
    c = (v @ face) / n
    return 1.0 / np.sqrt(c * c / (BODY_LONG * R) ** 2 + (1 - c * c) / (BODY_WIDE * R) ** 2)


HIT_BULLET = 1e6
HIT_MOB = 5e5


class Planner:
    BULLET_MARGIN = 0.8   # x R of room to keep from bullets
    NEAR_BULLET = 400.0
    NEAR_MOB = 600.0
    CROWD_WEIGHT = 40.0
    WALL = 6.0            # x R from an edge where it starts to cost
    WALL_WEIGHT = 900.0
    CORNER_WEIGHT = 3000.0
    SPAWN_WEIGHT = 800.0
    # HUD panels drawn over the arena (fractions of the window: x0, y0, x1, y1, weight). You can't be
    # seen under them, so the bot would lose track of you there: stay out.
    HUD = ((0.02, 0.036, 0.242, 0.117, 1500.0),    # HP panel, top left
           (0.754, 0.036, 0.995, 0.175, 1500.0),   # score panels, top right
           (0.20, 0.945, 0.82, 1.0, 1500.0),       # key hints, bottom
           (0.26, 0.067, 0.75, 0.21, 500.0))       # wave banner (only there between waves)
    LAP_WEIGHT = 150.0    # how much it likes running laps around the middle (x2 with the boss there)
    CENTER_WEIGHT = 60.0
    HEALTH_BONUS = 3000.0
    TURN_COST = 20.0
    SHOT_SPEED = 2.4      # your bullets' speed as a multiple of your walking speed (for aiming ahead)

    def __init__(self):
        self.prev = 0
        self.room = {}                    # learned: extra room per kind ("bullet", "grunt", ...), x normal
        self.mob_speed = dict(MOB_SPEED)  # learned: walking speed per kind as a fraction of yours
        self.style = {}                   # learned play style: bullet_room, mob_room, walls, laps, crowd (x1)
        self.body_scale = 1.0             # learned: your real hitbox size, x the UFO shape

    def plan(self, me, speed, tracks, W, H, latency=0.0, start=None):
        """me = (x, y, R): where you are now and your danger radius. start = where you will be when new
        keys take effect (or None = where you are). Returns (keys, aim point or None)."""
        x, y, R = me
        V = max(1.0, speed)
        sx, sy = start if start is not None else (x, y)
        p0 = np.array([min(max(sx, R), W - R), min(max(sy, R), H - R)])

        # positions along every plan: (81, 16, 2) at times 0, DT, ..., 15 DT after the keys take effect
        steps1 = np.arange(0, LEG1 + 1) * DT
        steps2 = np.arange(1, LEG2 + 1) * DT
        leg1 = p0[None, None, :] + DIRS[:, None, :] * V * steps1[None, :, None]            # (9, 6, 2)
        leg1 = np.clip(leg1, [R, R], [W - R, H - R])
        end1 = leg1[:, -1, :]
        leg2 = end1[:, None, None, :] + DIRS[None, :, None, :] * V * steps2[None, None, :, None]  # (9, 9, 10, 2)
        leg2 = np.clip(leg2, [R, R], [W - R, H - R])
        P = np.concatenate([np.repeat(leg1[:, None], 9, axis=1), leg2], axis=2).reshape(81, LEG1 + LEG2 + 1, 2)
        T = np.arange(LEG1 + LEG2 + 1) * DT                                                # (16,)
        w = 1.0 + np.clip(0.8 - T, 0, None)  # a hit soon is worse than one later
        cost = np.zeros(81)

        mobs = [t for t in tracks if t.kind in MOB_SPEED]
        spawns = [t for t in tracks if t.kind == "spawn"]
        aim_pt = self.aim(x, y, R, V, mobs, spawns)
        fx, fy = (aim_pt[0] - x, aim_pt[1] - y) if aim_pt is not None else (0.0, -1.0)
        fn = math.hypot(fx, fy) or 1.0
        face = np.array([fx / fn, fy / fn])
        Rb = R * self.body_scale
        body = P - face * BODY_BACK * Rb                   # center of the oval along every plan

        def size(v):
            return body_reach(v, face, Rb)

        bullets = [t for t in tracks if t.kind == "bullet"]
        health = [t for t in tracks if t.kind == "health"]
        reach = V * T[-1] + 2 * R

        # --- bullets: closest approach during every step (a fast bullet can't slip between checks)
        if bullets:
            b = np.array([[t.x, t.y, t.vx, t.vy, t.r] for t in bullets])
            far = np.hypot(b[:, 0] - p0[0], b[:, 1] - p0[1]) - np.hypot(b[:, 2], b[:, 3]) * (T[-1] + latency) - reach - b[:, 4]
            bm = self.BULLET_MARGIN * self.room.get("bullet", 1.0) * self.style.get("bullet_room", 1.0)
            b = b[far < bm * R]
            if len(b):
                bp = b[None, :, :2] + b[None, :, 2:4] * (T + latency)[:, None, None]       # (16, B, 2)
                D = body[:, :, None, :] - bp[None]                                         # (81, 16, B, 2)
                A, seg = D[:, :-1], D[:, 1:] - D[:, :-1]
                u = np.clip(-(A * seg).sum(-1) / ((seg * seg).sum(-1) + 1e-9), 0, 1)
                closest = A + u[..., None] * seg
                gap = np.sqrt((closest ** 2).sum(-1)) - size(closest) - b[None, None, :, 4]  # (81, 15, B)
                m = bm * R
                wt = w[1:][None, :, None]
                cost += (np.where(gap < 0, HIT_BULLET, 0.0) * wt).sum(axis=(1, 2))
                near = np.clip((m - gap) / m, 0, 1) ** 2 * self.NEAR_BULLET
                cost += (near * wt).sum(axis=(1, 2))

        # --- mobs: chasers walk toward where you'll be; others keep moving as they do
        if mobs:
            mp = np.array([[t.x, t.y] for t in mobs])
            mv = np.array([[t.vx, t.vy] for t in mobs])
            mr = np.array([t.r for t in mobs])
            # (the boss walks slowly; its sudden charges are covered by keeping a big distance)
            ms = self.mob_speed
            spd = np.array([max(t.speed if t.age >= 3 else 0.0, ms[t.kind] * V * (0.8 if t.age >= 3 else 1.0))
                            if t.kind != "boss" else max(t.speed if t.age >= 3 else 0.0, ms["boss"] * V)
                            for t in mobs])
            chase = np.array([t.kind in CHASERS for t in mobs])
            margin = np.array([MARGIN[t.kind] * self.room.get(t.kind, 1.0) for t in mobs]) * R * \
                self.style.get("mob_room", 1.0)
            tt = (T + latency)[None, :, None]                                              # (1, 16, 1)
            diff = P[:, :, None, :] - mp[None, None]                                       # (81, 16, M, 2)
            dist = np.sqrt((diff ** 2).sum(-1)) + 1e-6
            walked = np.minimum(dist, spd[None, None, :] * tt)
            chase_pos = mp[None, None] + diff / dist[..., None] * walked[..., None]
            drift_pos = (mp[None] + mv[None] * (T + latency)[:, None, None])[None]         # (1, 16, M, 2)
            pos = np.where(chase[None, None, :, None], chase_pos, drift_pos)
            rel = body[:, :, None, :] - pos
            gap = np.sqrt((rel ** 2).sum(-1)) - size(rel) - mr[None, None]
            cost += (np.where(gap < 0, HIT_MOB, 0.0) * w[None, :, None]).sum(axis=(1, 2))
            near = np.clip((margin[None, None] - gap) / margin[None, None], 0, 1) ** 2 * self.NEAR_MOB
            cost += (near * w[None, :, None]).sum(axis=(1, 2))
            # where each plan ends: away from crowds
            end = P[:, -1, :]
            g_end = np.sqrt(((end[:, None, :] - mp[None]) ** 2).sum(-1)) - mr[None]
            wk = np.array([CROWD[t.kind] for t in mobs])
            cost += (wk[None] * 4 * R / np.maximum(g_end, R / 2)).sum(-1) * self.CROWD_WEIGHT * \
                self.style.get("crowd", 1.0)

        # --- don't stand where an enemy is about to appear
        if spawns:
            sp = np.array([[t.x, t.y, t.r] for t in spawns])
            end = P[:, -1, :]
            d = np.sqrt(((end[:, None, :] - sp[None, :, :2]) ** 2).sum(-1))
            cost += (np.clip((sp[None, :, 2] * 0.8 + 2 * R - d) / (sp[None, :, 2] * 0.8 + 2 * R), 0, 1) ** 2).sum(-1) * self.SPAWN_WEIGHT

        # --- walls and corners (each edge counts, so corners count twice), and a pull to the middle
        end = P[:, -1, :]
        walls = self.style.get("walls", 1.0)
        for d in (end[:, 0], W - end[:, 0], end[:, 1], H - end[:, 1]):
            cost += np.clip((self.WALL * R - d) / (self.WALL * R), 0, 1) ** 2 * self.WALL_WEIGHT * walls
        # corners trap you: extra cost when close to two edges at once
        C = 0.25 * min(W, H)
        near_x = np.clip((C - np.minimum(end[:, 0], W - end[:, 0])) / C, 0, 1)
        near_y = np.clip((C - np.minimum(end[:, 1], H - end[:, 1])) / C, 0, 1)
        cost += near_x * near_y * self.CORNER_WEIGHT * walls
        cdist = np.hypot(end[:, 0] - W / 2, end[:, 1] - H / 2) / (0.5 * min(W, H))
        cost += cdist ** 2 * self.CENTER_WEIGHT

        # --- HUD panels: share of the plan spent under one (grown by your size)
        for x0, y0, x1, y1, wgt in self.HUD:
            inside = ((P[..., 0] > x0 * W - R) & (P[..., 0] < x1 * W + R) &
                      (P[..., 1] > y0 * H - R) & (P[..., 1] < y1 * H + R))
            cost += inside[:, 1:].mean(axis=1) * wgt

        # --- green health circles on the way
        if health:
            hp = np.array([[t.x, t.y, t.r] for t in health])
            dd = np.sqrt(((P[:, :, None, :] - hp[None, None, :, :2]) ** 2).sum(-1)) - R - hp[None, None, :, 2]
            cost -= (dd.min(axis=1) < 0).any(axis=1) * self.HEALTH_BONUS

        # --- laps around the middle: running a big circle keeps chasers behind you and keeps you out
        # of corners (where the boss and its grunts would trap you)
        boss = min((t for t in mobs if t.kind == "boss"), key=lambda t: math.hypot(t.x - x, t.y - y), default=None)
        if boss is not None:
            # boss wave: circle around the boss at a safe distance, on the side toward the middle
            lap = self.LAP_WEIGHT * 2.0
            pref0 = self._around_boss(p0, boss, W, H)
            pref1 = np.array([self._around_boss(e, boss, W, H) for e in end1])
        else:
            lap = self.LAP_WEIGHT
            pref0 = self._lap_dir(p0, W, H)
            pref1 = np.array([self._lap_dir(e, W, H) for e in end1])                    # (9, 2)
        lap *= self.style.get("laps", 1.0)
        first = np.repeat(np.arange(9), 9)
        second = np.tile(np.arange(9), 9)
        cost += (1 - DIRS[first] @ pref0) * lap
        cost += (1 - (DIRS[second] * pref1[first]).sum(-1)) * lap * 0.5

        cost += np.where(first != self.prev, self.TURN_COST, 0.0)
        self.last_cost = cost
        best = int(np.argmin(cost))
        self.prev = int(first[best])
        return KEYS[self.prev], aim_pt

    def _lap_dir(self, p, W, H):
        """Direction of a lap around the middle (an ellipse at 1/3 of the arena), steering back onto it."""
        cx, cy, A, B = W / 2, H / 2, W * 0.33, H * 0.33
        u, v = (p[0] - cx) / A, (p[1] - cy) / B
        rho = math.hypot(u, v) or 1e-6
        d = np.array([-v / rho * A + u / rho * (1 - rho) * 1.5 * A, u / rho * B + v / rho * (1 - rho) * 1.5 * B])
        return d / (np.linalg.norm(d) or 1.0)

    def _around_boss(self, p, boss, W, H):
        away = np.array([p[0] - boss.x, p[1] - boss.y])
        d = np.linalg.norm(away) or 1.0
        away /= d
        tangent = np.array([-away[1], away[0]])
        to_mid = np.array([W / 2 - p[0], H / 2 - p[1]])
        if tangent @ to_mid < 0:
            tangent = -tangent  # go around on the side with more room
        keep = BOSS_KEEP * H + boss.r
        radial = np.clip((keep - d) / (0.3 * keep), -1, 1)  # too close: out; too far: back in a bit
        mid = to_mid / max(np.linalg.norm(to_mid), 0.25 * min(W, H))
        v = tangent + 1.2 * radial * away + 0.6 * mid
        return v / (np.linalg.norm(v) or 1.0)

    def aim(self, x, y, R, V, mobs, spawns=()):
        """Yellow mobs first, then orange shooters, then whatever is closing in; aimed ahead of it.
        Prefire: with nothing more urgent, shoot at a warning ring so the enemy is hit as it appears."""
        target, best = None, math.inf
        for t in spawns:
            score = math.hypot(t.x - x, t.y - y) / SPAWN_PRIORITY
            if score < best:
                target, best = t, score
        for t in mobs:
            prio = AIM_PRIORITY[t.kind]
            if t.kind == "tank" and math.hypot(t.x - x, t.y - y) < 8 * R:
                prio = 0.2  # it splits into 3 fast tiny ones: only finish it off from a distance
            if t.kind in ("grunt", "tiny") and math.hypot(t.x - x, t.y - y) < 6 * R:
                prio = 3.5  # about to reach you
            score = math.hypot(t.x - x, t.y - y) / prio
            if score < best:
                target, best = t, score
        if target is None:
            return None
        tx, ty = target.x, target.y
        shot = self.SHOT_SPEED * V
        for _ in range(3):
            ft = math.hypot(tx - x, ty - y) / shot
            tx, ty = target.x + target.vx * ft, target.y + target.vy * ft
        return tx, ty


# ---------------------------------------------------------------------- tuned settings
# tests/tune.py tunes the settings above by playing thousands of fake games and writes the best ones
# to tuned.py; they replace the hand-picked values here.
TUNABLE = (["BULLET_MARGIN", "NEAR_BULLET", "NEAR_MOB", "CROWD_WEIGHT", "WALL", "WALL_WEIGHT", "CORNER_WEIGHT",
            "LAP_WEIGHT", "CENTER_WEIGHT", "HEALTH_BONUS", "TURN_COST", "BOSS_KEEP"] +
           [f"MARGIN.{k}" for k in MARGIN] + [f"AIM_PRIORITY.{k}" for k in AIM_PRIORITY])


def get_setting(name):
    if "." in name:
        table, key = name.split(".")
        return globals()[table][key]
    return getattr(Planner, name) if hasattr(Planner, name) else globals()[name]


def set_setting(name, value):
    if "." in name:
        table, key = name.split(".")
        globals()[table][key] = value
    elif hasattr(Planner, name):
        setattr(Planner, name, value)
    else:
        globals()[name] = value


try:
    from tuned import TUNED
except ImportError:
    TUNED = {}
for _name, _value in TUNED.items():
    if _name in TUNABLE:
        set_setting(_name, _value)
