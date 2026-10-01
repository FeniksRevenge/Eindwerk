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
# Bump when the dodging logic changes enough that settings trained for the old one don't fit anymore:
# saved training ("brain_params") from another version is then ignored.
BRAIN_VERSION = 3
S = math.sqrt(0.5)
DIRS = np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [S, S], [S, -S], [-S, S], [-S, -S]])
DIR_KEYS = [(), ("d",), ("a",), ("s",), ("w",), ("s", "d"), ("w", "d"), ("s", "a"), ("w", "a")]

STEPS1 = np.arange(1, 11) * 0.04   # first move: 0.4 s
STEPS2 = np.arange(1, 9) * 0.05    # follow-up move: another 0.4 s

# Default speeds in game units per second (used until the real ones have been measured).
DEFAULT_PLAYER_SPEED = 260.0
DEFAULT_MOB_SPEED = {"grunt": 70.0, "runner": 90.0, "tank": 42.0, "tank_mini": 110.0, "shooter": 105.0, "boss": 48.0}
FAST = 250.0  # game units/s: an "orange shooter" moving faster than this is really an orange bullet
BULLETLIKE = 170.0  # game units/s: mobs are slower than this (fastest: tiny tanks ~110), bullets faster


class Brain:
    BULLET_MARGIN = 30
    MOB_MARGIN = 60
    BOSS_MARGIN = 60    # extra distance to keep from the boss (bigger made it hide in corners)
    CROWD_WEIGHT = 2500
    WALL_MARGIN = 140
    WALL_WEIGHT = 0.35
    ORBIT_WEIGHT = 150
    HEALTH_PULL = 2000    # how strongly it heads for a green health circle
    HEALTH_REWARD = 30000  # how much picking one up on the way is worth (+2 HP; a hit costs 1e6)
    EDGE_MARGIN = 190     # distance from each edge where moving on costs extra (corners count twice)
    EDGE_WEIGHT = 0.25
    BOSS_AWAY = 0.35      # boss nearby: mostly circle around it, only a little straight away from it
    BOSS_CENTER = 2.5     # ... and lean toward the middle so the circling doesn't end in a corner

    def __init__(self, bullet_speed=820.0, params=None, **overrides):
        self.bullet_speed = bullet_speed  # speed of YOUR bullets, game units/s (for leading shots)
        for name, value in {**(params or {}), **overrides}.items():  # tuned values
            if hasattr(Brain, name):
                setattr(self, name, float(value))
        self.prev = np.zeros(2)
        self.orbit_dir = 1

    @staticmethod
    def _mob_speed(t, k, player_speed):
        """Speed to assume for a mob, in game units/s. The boss is assumed to be able to rush."""
        base = DEFAULT_MOB_SPEED[t.kind]
        measured = math.hypot(t.vx, t.vy) / k if t.age > 3 else base * 1.2
        if t.kind == "boss":
            return max(measured, t.vmax / k, 0.7 * player_speed)
        return max(measured, base * 0.8)

    # How much the bot dislikes being near each kind (crowd cost). Shooters make bullets: yellow ones
    # (all directions) most, orange ones less; the boss most of all.
    DANGER = {"boss": 3.6, "runner": 1.6, "shooter": 1.3}

    BULLET_HIT = 1e6   # getting hit costs far more than any "too close" penalty (boss distance included)
    MOB_HIT = 3e5

    def _leg(self, start, t0, steps, speed, W, H, pr, mobs, bullets, latency=0.0, health=None):
        """Danger of running straight in each of the 9 directions from each start point.
        start: (N, 2). Returns cost (N, 9) and end points (N, 9, 2)."""
        P = start[:, None, None, :] + DIRS[None, :, None, :] * speed * steps[None, None, :, None]
        P[..., 0] = np.clip(P[..., 0], pr, W - pr)
        P[..., 1] = np.clip(P[..., 1], pr, H - pr)
        T = t0 + steps
        urg = np.maximum(0.3, 1.4 - T)[None, None, :, None]  # near-future danger matters more
        T = T + latency  # things keep moving while the bot reads the screen and presses keys
        cost = np.zeros(P.shape[:2])

        if len(bullets["pos"]):
            # Closest approach during each time step, not just at the sampled moments: a fast bullet
            # coming head-on moves further per step than the hit distance and could slip "through".
            T0 = np.concatenate([[t0 + latency], T])                                         # (S+1,)
            P0 = np.concatenate([np.broadcast_to(start[:, None, None, :], (P.shape[0], 9, 1, 2)), P], axis=2)
            bp = bullets["pos"][None] + bullets["vel"][None] * T0[:, None, None]         # (S+1, B, 2)
            D = P0[:, :, :, None, :] - bp[None, None]                                    # (N, 9, S+1, B, 2)
            A, seg = D[:, :, :-1], D[:, :, 1:] - D[:, :, :-1]
            u = np.clip(-(A[..., 0] * seg[..., 0] + A[..., 1] * seg[..., 1]) /
                        (seg[..., 0] ** 2 + seg[..., 1] ** 2 + 1e-9), 0.0, 1.0)
            cx, cy = A[..., 0] + u * seg[..., 0], A[..., 1] + u * seg[..., 1]
            gap = np.sqrt(cx ** 2 + cy ** 2) - pr - bullets["r"]
            m = self.BULLET_MARGIN
            near = (m - np.maximum(gap, 0)) ** 2 * 4
            c = np.where(gap < 0, self.BULLET_HIT, np.where(gap < m, near, 0.0))
            cost += (c * urg).sum(axis=(2, 3))

        if len(mobs["pos"]):
            mp = mobs["pos"]
            diff = P[:, :, :, None, :] - mp                                                # (N, 9, S, M, 2)
            md = np.sqrt(diff[..., 0] ** 2 + diff[..., 1] ** 2) + 1e-6
            step = np.minimum(md, mobs["speed"][None, None, None, :] * T[None, None, :, None])
            chase = mp + diff / md[..., None] * step[..., None]
            drift = mp[None] + mobs["vel"][None] * T[:, None, None]                        # (S, M, 2)
            pos = np.where(mobs["chaser"][:, None], chase, drift[None, None])
            dd = P[:, :, :, None, :] - pos
            gap = np.sqrt(dd[..., 0] ** 2 + dd[..., 1] ** 2) - pr - mobs["r"]
            m = mobs["margin"]
            near = (m - np.maximum(gap, 0)) ** 2 * 1.5
            c = np.where(gap < 0, self.MOB_HIT, np.where(gap < m, near, 0.0))
            cost += (c * urg).sum(axis=(2, 3))
        if health is not None and len(health["pos"]):
            # Walking over a green health circle on the way is worth a lot (+2 HP).
            hd = P[:, :, :, None, :] - health["pos"]                                     # (N, 9, S, K, 2)
            got = (hd[..., 0] ** 2 + hd[..., 1] ** 2 < (pr + health["r"]) ** 2).any(axis=2)  # (N, 9, K)
            cost -= (got * self.HEALTH_REWARD).sum(axis=-1)
        # Edges and corners along the way: each edge adds its own penalty, so corners cost double.
        ex = np.maximum(0, self.EDGE_MARGIN - np.minimum(P[..., 0], W - P[..., 0]))
        ey = np.maximum(0, self.EDGE_MARGIN - np.minimum(P[..., 1], H - P[..., 1]))
        cost += ((ex ** 2 + ey ** 2) * self.EDGE_WEIGHT * urg[..., 0]).sum(axis=2)
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

    def think(self, player, player_speed, tracks, width, height, latency=0.0, start_xy=None):
        """player: (x, y, r) in screen pixels of the play area. tracks: vision.Track list.
        Returns (keys to hold, (aim_x, aim_y) in play-area pixels or None, fire?)."""
        px, py, prad = player
        k = max(prad, 1) / REF_R  # pixels per game unit
        W, H = width / k, height / k
        p = np.array([px / k, py / k])
        pr = REF_R
        speed = player_speed / k

        # Anything (not the boss) flying at bullet speed is dodged like a bullet, whatever it was taken
        # for (e.g. two red bullets touching can look like a grunt).
        flying = [t for t in tracks if t.kind in DEFAULT_MOB_SPEED and t.kind != "boss" and t.age > 2
                  and math.hypot(t.vx, t.vy) / k > BULLETLIKE]
        mob_t = [t for t in tracks if t.kind in DEFAULT_MOB_SPEED and t not in flying]
        bul_t = [t for t in tracks if t.kind == "enemy_bullet"] + flying
        pickups = [t for t in tracks if t.kind == "health"]
        mobs = {
            "pos": np.array([[t.x / k, t.y / k] for t in mob_t]).reshape(-1, 2),
            "vel": np.array([[t.vx / k, t.vy / k] for t in mob_t]).reshape(-1, 2),
            "r": np.array([t.r / k for t in mob_t]),
            "speed": np.array([self._mob_speed(t, k, speed) for t in mob_t]),
            "margin": np.array([self.MOB_MARGIN + (self.BOSS_MARGIN if t.kind == "boss" else 0) for t in mob_t]),
            # Shooters (orange, yellow) keep their distance, so predict them by their own movement.
            "chaser": np.array([t.kind not in ("shooter", "runner") for t in mob_t], dtype=bool),
            "weight": np.array([self.DANGER.get(t.kind, 1.0) for t in mob_t]),
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
        pull = self.ORBIT_WEIGHT
        bosses = [t for t in mob_t if t.kind == "boss"]
        boss = min(bosses, key=lambda t: math.hypot(t.x - px, t.y - py)) if bosses else None
        if boss is not None and math.hypot(boss.x - px, boss.y - py) / k < 700:
            # Boss nearby: circle away from it instead of running laps through the middle.
            away = np.array([p[0] - boss.x / k, p[1] - boss.y / k])
            away /= np.linalg.norm(away) or 1
            tangent = np.array([-away[1], away[0]]) * self.orbit_dir
            center = np.array([W / 2 - p[0], H / 2 - p[1]])
            center /= max(np.linalg.norm(center), W * 0.25)  # stronger the further from the middle
            pref = tangent + self.BOSS_AWAY * away + self.BOSS_CENTER * center
            pref /= np.linalg.norm(pref) or 1
            pull = self.ORBIT_WEIGHT * 2
        # Green health circles: go get the nearest one (also during a boss fight, unless it's right next
        # to the boss). The danger checks still keep the way there safe.
        safe = [t for t in pickups if boss is None or
                math.hypot(t.x - boss.x, t.y - boss.y) / k > boss.r / k + 150]
        if safe:
            hp = min(safe, key=lambda t: math.hypot(t.x - px, t.y - py))
            to = np.array([hp.x / k - p[0], hp.y / k - p[1]])
            if np.linalg.norm(to) > 1:
                pref = to / np.linalg.norm(to)
                pull = self.HEALTH_PULL

        # During the reaction delay the player keeps moving with the keys we're still holding,
        # so plan from where it will be when the new keys land, not from where it is now.
        # start_xy: where the caller knows the player will be (it replays the keys already sent).
        start = np.array([start_xy[0] / k, start_xy[1] / k]) if start_xy is not None else p + self.prev * speed * latency
        start = np.array([min(max(start[0], pr), W - pr), min(max(start[1], pr), H - pr)])
        # Only things that could get within their margin during the 0.8 s look-ahead matter for the
        # moves (the rest add exactly zero), so leave the far ones out: same decision, much less work.
        horizon = STEPS1[-1] + STEPS2[-1] + latency
        reach = speed * (STEPS1[-1] + STEPS2[-1]) + pr
        near_b, near_m = bullets, mobs
        if len(bullets["pos"]):
            d = np.hypot(bullets["pos"][:, 0] - start[0], bullets["pos"][:, 1] - start[1])
            vb = np.hypot(bullets["vel"][:, 0], bullets["vel"][:, 1])
            keep = d - reach - vb * horizon - bullets["r"] <= self.BULLET_MARGIN
            near_b = {k: v[keep] for k, v in bullets.items()}
        if len(mobs["pos"]):
            d = np.hypot(mobs["pos"][:, 0] - start[0], mobs["pos"][:, 1] - start[1])
            vm = np.maximum(mobs["speed"], np.hypot(mobs["vel"][:, 0], mobs["vel"][:, 1]))
            keep = d - reach - vm * horizon - mobs["r"] <= mobs["margin"]
            near_m = {k: v[keep] for k, v in mobs.items()}
        health = {"pos": np.array([[t.x / k, t.y / k] for t in safe]).reshape(-1, 2),
                  "r": np.array([t.r / k for t in safe])}
        c1, end1 = self._leg(start[None], 0.0, STEPS1, speed, W, H, pr, near_m, near_b, latency, health)
        c2, end2 = self._leg(end1[0], 0.4, STEPS2, speed, W, H, pr, near_m, near_b, latency, health)
        follow = (c2 * 0.7 + self._spot(end2, W, H, mobs)).min(axis=1)
        total = c1[0] + follow
        total += (1 - DIRS @ pref) * pull
        moving = np.any(DIRS != 0, axis=1)
        total += np.where(moving, (1 - DIRS @ self.prev) * 12, 0)
        best = int(np.argmin(total))
        self.prev = DIRS[best]

        # Aim: yellow mobs first, then orange shooters (they make the bullets), unless something else is
        # about to reach us (score = roughly seconds until it matters).
        target, best_score = None, math.inf
        for t in mob_t:
            if not (0 <= t.x <= width and 0 <= t.y <= height):
                continue
            if t.kind == "shooter" and t.age > 2 and math.hypot(t.vx, t.vy) / k > FAST:
                continue  # an orange bullet, not worth shooting at
            gap = (math.hypot(t.x - px, t.y - py) - t.r) / k
            if t.kind == "boss":
                score = gap / 80 + 1
            elif t.kind == "runner":  # yellow: shoots in all directions, the most dangerous: first
                score = gap / 150 * 0.3
            elif t.kind == "shooter":  # orange: shoots at you, take it out early too
                score = gap / 150 * 0.6
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
