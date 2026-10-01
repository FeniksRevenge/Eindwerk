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
    LAP_WEIGHT = 150.0    # how much it likes running laps around the middle (x2 with the boss there)
    CENTER_WEIGHT = 60.0
    HEALTH_BONUS = 3000.0
    TURN_COST = 20.0
    SHOT_SPEED = 2.4      # your bullets' speed as a multiple of your walking speed (for aiming ahead)

    def __init__(self):
        self.prev = 0

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

        bullets = [t for t in tracks if t.kind == "bullet"]
        mobs = [t for t in tracks if t.kind in MOB_SPEED]
        health = [t for t in tracks if t.kind == "health"]
        spawns = [t for t in tracks if t.kind == "spawn"]
        reach = V * T[-1] + R

        # --- bullets: closest approach during every step (a fast bullet can't slip between checks)
        if bullets:
            b = np.array([[t.x, t.y, t.vx, t.vy, t.r] for t in bullets])
            far = np.hypot(b[:, 0] - p0[0], b[:, 1] - p0[1]) - np.hypot(b[:, 2], b[:, 3]) * (T[-1] + latency) - reach - b[:, 4]
            b = b[far < self.BULLET_MARGIN * R]
            if len(b):
                bp = b[None, :, :2] + b[None, :, 2:4] * (T + latency)[:, None, None]       # (16, B, 2)
                D = P[:, :, None, :] - bp[None]                                            # (81, 16, B, 2)
                A, seg = D[:, :-1], D[:, 1:] - D[:, :-1]
                u = np.clip(-(A * seg).sum(-1) / ((seg * seg).sum(-1) + 1e-9), 0, 1)
                closest = A + u[..., None] * seg
                gap = np.sqrt((closest ** 2).sum(-1)) - R - b[None, None, :, 4]           # (81, 15, B)
                m = self.BULLET_MARGIN * R
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
            spd = np.array([max(t.speed if t.age >= 3 else 0.0, MOB_SPEED[t.kind] * V * (0.8 if t.age >= 3 else 1.0))
                            if t.kind != "boss" else max(t.speed if t.age >= 3 else 0.0, MOB_SPEED["boss"] * V)
                            for t in mobs])
            chase = np.array([t.kind in CHASERS for t in mobs])
            margin = np.array([MARGIN[t.kind] for t in mobs]) * R
            tt = (T + latency)[None, :, None]                                              # (1, 16, 1)
            diff = P[:, :, None, :] - mp[None, None]                                       # (81, 16, M, 2)
            dist = np.sqrt((diff ** 2).sum(-1)) + 1e-6
            walked = np.minimum(dist, spd[None, None, :] * tt)
            chase_pos = mp[None, None] + diff / dist[..., None] * walked[..., None]
            drift_pos = (mp[None] + mv[None] * (T + latency)[:, None, None])[None]         # (1, 16, M, 2)
            pos = np.where(chase[None, None, :, None], chase_pos, drift_pos)
            gap = np.sqrt(((P[:, :, None, :] - pos) ** 2).sum(-1)) - R - mr[None, None]
            cost += (np.where(gap < 0, HIT_MOB, 0.0) * w[None, :, None]).sum(axis=(1, 2))
            near = np.clip((margin[None, None] - gap) / margin[None, None], 0, 1) ** 2 * self.NEAR_MOB
            cost += (near * w[None, :, None]).sum(axis=(1, 2))
            # where each plan ends: away from crowds
            end = P[:, -1, :]
            g_end = np.sqrt(((end[:, None, :] - mp[None]) ** 2).sum(-1)) - mr[None]
            wk = np.array([CROWD[t.kind] for t in mobs])
            cost += (wk[None] * 4 * R / np.maximum(g_end, R / 2)).sum(-1) * self.CROWD_WEIGHT

        # --- don't stand where an enemy is about to appear
        if spawns:
            sp = np.array([[t.x, t.y, t.r] for t in spawns])
            end = P[:, -1, :]
            d = np.sqrt(((end[:, None, :] - sp[None, :, :2]) ** 2).sum(-1))
            cost += (np.clip((sp[None, :, 2] * 0.8 + 2 * R - d) / (sp[None, :, 2] * 0.8 + 2 * R), 0, 1) ** 2).sum(-1) * self.SPAWN_WEIGHT

        # --- walls and corners (each edge counts, so corners count twice), and a pull to the middle
        end = P[:, -1, :]
        for d in (end[:, 0], W - end[:, 0], end[:, 1], H - end[:, 1]):
            cost += np.clip((self.WALL * R - d) / (self.WALL * R), 0, 1) ** 2 * self.WALL_WEIGHT
        # corners trap you: extra cost when close to two edges at once
        C = 0.25 * min(W, H)
        near_x = np.clip((C - np.minimum(end[:, 0], W - end[:, 0])) / C, 0, 1)
        near_y = np.clip((C - np.minimum(end[:, 1], H - end[:, 1])) / C, 0, 1)
        cost += near_x * near_y * self.CORNER_WEIGHT
        cdist = np.hypot(end[:, 0] - W / 2, end[:, 1] - H / 2) / (0.5 * min(W, H))
        cost += cdist ** 2 * self.CENTER_WEIGHT

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
        first = np.repeat(np.arange(9), 9)
        second = np.tile(np.arange(9), 9)
        cost += (1 - DIRS[first] @ pref0) * lap
        cost += (1 - (DIRS[second] * pref1[first]).sum(-1)) * lap * 0.5

        cost += np.where(first != self.prev, self.TURN_COST, 0.0)
        best = int(np.argmin(cost))
        self.prev = int(first[best])
        return KEYS[self.prev], self.aim(x, y, R, V, mobs, spawns)

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
