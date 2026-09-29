"""
Decision making: given where everything is, pick which WASD keys to hold and where to aim.

Same idea as the in-browser bot, but limited to the 8 directions WASD can actually do:
for every direction (plus standing still) it simulates the next ~0.8 seconds, including one
follow-up move, and picks the one that stays furthest from bullets, mobs and walls.

All distances are converted to "game units" where the player's radius is 13, so the numbers
below work no matter how big the game is on your screen.
"""

import math

import numpy as np

REF_R = 13.0
S = math.sqrt(0.5)
DIRS = np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [S, S], [S, -S], [-S, S], [-S, -S]])
DIR_KEYS = [(), ("d",), ("a",), ("s",), ("w",), ("s", "d"), ("w", "d"), ("s", "a"), ("w", "a")]

STEPS1 = np.arange(1, 11) * 0.04   # first move: 0.4 s
STEPS2 = np.arange(1, 9) * 0.05    # follow-up move: another 0.4 s

# Default speeds in game units per second (used until the real ones have been measured).
DEFAULT_PLAYER_SPEED = 260.0
DEFAULT_MOB_SPEED = {"grunt": 70.0, "runner": 135.0, "tank": 42.0, "shooter": 105.0, "boss": 48.0}


class Brain:
    BULLET_MARGIN = 22
    MOB_MARGIN = 60
    CROWD_WEIGHT = 2500
    WALL_MARGIN = 140
    WALL_WEIGHT = 0.35
    ORBIT_WEIGHT = 150

    def __init__(self, bullet_speed=820.0):
        self.bullet_speed = bullet_speed  # speed of YOUR bullets, game units/s (for leading shots)
        self.prev = np.zeros(2)
        self.orbit_dir = 1

    def _leg(self, start, t0, steps, speed, W, H, pr, mobs, bullets):
        """Danger of running straight in each of the 9 directions from each start point.
        start: (N, 2). Returns cost (N, 9) and end points (N, 9, 2)."""
        P = start[:, None, None, :] + DIRS[None, :, None, :] * speed * steps[None, None, :, None]
        P[..., 0] = np.clip(P[..., 0], pr, W - pr)
        P[..., 1] = np.clip(P[..., 1], pr, H - pr)
        T = t0 + steps
        urg = np.maximum(0.3, 1.4 - T)[None, None, :, None]  # near-future danger matters more
        cost = np.zeros(P.shape[:2])

        if len(bullets["pos"]):
            bp = bullets["pos"][None] + bullets["vel"][None] * T[:, None, None]          # (S, B, 2)
            gap = np.linalg.norm(P[:, :, :, None, :] - bp[None, None], axis=-1) - pr - bullets["r"]
            m = self.BULLET_MARGIN
            c = np.where(gap < 0, 20000.0, np.where(gap < m, (m - np.maximum(gap, 0)) ** 2 * 4, 0.0))
            cost += (c * urg).sum(axis=(2, 3))

        if len(mobs["pos"]):
            mp = mobs["pos"]
            diff = P[:, :, :, None, :] - mp                                                # (N, 9, S, M, 2)
            md = np.linalg.norm(diff, axis=-1) + 1e-6
            step = np.minimum(md, mobs["speed"][None, None, None, :] * T[None, None, :, None])
            chase = mp + diff / md[..., None] * step[..., None]
            drift = mp[None] + mobs["vel"][None] * T[:, None, None]                        # (S, M, 2)
            pos = np.where(mobs["chaser"][:, None], chase, drift[None, None])
            gap = np.linalg.norm(P[:, :, :, None, :] - pos, axis=-1) - pr - mobs["r"]
            m = self.MOB_MARGIN
            c = np.where(gap < 0, 20000.0, np.where(gap < m, (m - np.maximum(gap, 0)) ** 2 * 1.5, 0.0))
            cost += (c * urg).sum(axis=(2, 3))
        return cost, P[:, :, -1, :]

    def _spot(self, pts, W, H, mobs):
        """How bad it is to end up at pts (..., 2): near the crowd or near a wall/corner."""
        cost = np.zeros(pts.shape[:-1])
        if len(mobs["pos"]):
            gap = np.maximum(1, np.linalg.norm(pts[..., None, :] - mobs["pos"], axis=-1) - mobs["r"])
            cost += (mobs["weight"] * self.CROWD_WEIGHT / (gap + 20)).sum(axis=-1)
        wall = np.minimum(np.minimum(pts[..., 0], W - pts[..., 0]), np.minimum(pts[..., 1], H - pts[..., 1]))
        cost += np.where(wall < self.WALL_MARGIN, (self.WALL_MARGIN - wall) ** 2 * self.WALL_WEIGHT, 0)
        return cost

    def think(self, player, player_speed, tracks, width, height):
        """player: (x, y, r) in screen pixels of the play area. tracks: vision.Track list.
        Returns (keys to hold, (aim_x, aim_y) in play-area pixels or None, fire?)."""
        px, py, prad = player
        k = max(prad, 1) / REF_R  # pixels per game unit
        W, H = width / k, height / k
        p = np.array([px / k, py / k])
        pr = REF_R
        speed = player_speed / k

        mob_t = [t for t in tracks if t.kind != "enemy_bullet"]
        bul_t = [t for t in tracks if t.kind == "enemy_bullet"]
        mobs = {
            "pos": np.array([[t.x / k, t.y / k] for t in mob_t]).reshape(-1, 2),
            "vel": np.array([[t.vx / k, t.vy / k] for t in mob_t]).reshape(-1, 2),
            "r": np.array([t.r / k for t in mob_t]),
            "speed": np.array([max(math.hypot(t.vx, t.vy) / k, DEFAULT_MOB_SPEED[t.kind] * 0.8) if t.age > 3
                               else DEFAULT_MOB_SPEED[t.kind] * 1.2 for t in mob_t]),
            "chaser": np.array([t.kind != "shooter" for t in mob_t], dtype=bool),
            "weight": np.array([3.6 if t.kind == "boss" else 1.0 for t in mob_t]),
        }
        bullets = {
            "pos": np.array([[t.x / k, t.y / k] for t in bul_t]).reshape(-1, 2),
            "vel": np.array([[t.vx / k, t.vy / k] for t in bul_t]).reshape(-1, 2),
            "r": np.array([t.r / k for t in bul_t]),
        }

        # Preferred heading: laps around an ellipse in the middle, so chasers trail behind.
        cx, cy = W / 2, H / 2
        A, B = W * 0.33, H * 0.33
        u, v = (p[0] - cx) / A, (p[1] - cy) / B
        rho = math.hypot(u, v) or 1e-6
        pref = np.array([-v / rho * A * self.orbit_dir + u / rho * (1 - rho) * 700,
                         u / rho * B * self.orbit_dir + v / rho * (1 - rho) * 700])
        pref /= np.linalg.norm(pref) or 1

        c1, end1 = self._leg(p[None], 0.0, STEPS1, speed, W, H, pr, mobs, bullets)
        c2, end2 = self._leg(end1[0], 0.4, STEPS2, speed, W, H, pr, mobs, bullets)
        follow = (c2 * 0.7 + self._spot(end2, W, H, mobs)).min(axis=1)
        total = c1[0] + follow
        total += (1 - DIRS @ pref) * self.ORBIT_WEIGHT
        moving = np.any(DIRS != 0, axis=1)
        total += np.where(moving, (1 - DIRS @ self.prev) * 12, 0)
        best = int(np.argmin(total))
        self.prev = DIRS[best]

        # Aim at whatever would reach us first. Shooters count extra because they shoot back.
        target, best_score = None, math.inf
        for t in mob_t:
            if not (0 <= t.x <= width and 0 <= t.y <= height):
                continue
            gap = (math.hypot(t.x - px, t.y - py) - t.r) / k
            if t.kind == "boss":
                score = gap / 80 + 1
            elif t.kind == "shooter":
                score = gap / 150 * 0.5
            else:
                score = gap / DEFAULT_MOB_SPEED[t.kind]
            if score < best_score:
                target, best_score = t, score
        aim = None
        if target is not None:
            tx, ty = target.x, target.y
            for _ in range(3):  # lead the shot
                tt = math.hypot(tx - px, ty - py) / (self.bullet_speed * k)
                tx, ty = target.x + target.vx * tt, target.y + target.vy * tt
            aim = (tx, ty)
        return DIR_KEYS[best], aim, target is not None
