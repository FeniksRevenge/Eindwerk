"""
Following things from one screenshot to the next, to know where each one is going and how fast.
"""

import math

KINDS = ("bullet", "grunt", "shooter", "yellow", "tank", "tiny", "boss", "health")


class Track:
    __slots__ = ("kind", "x", "y", "r", "vx", "vy", "age", "missing", "vmax", "id")
    _next_id = 0

    def __init__(self, kind, x, y, r, vx=0.0, vy=0.0):
        self.kind, self.x, self.y, self.r, self.vx, self.vy = kind, x, y, r, vx, vy
        self.age = 0        # how many times it has been seen again (0 = new, speed is only a guess)
        self.missing = 0
        self.vmax = 0.0     # fastest speed seen (the boss rushes)
        Track._next_id += 1
        self.id = Track._next_id

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)


class Tracker:
    def __init__(self):
        self.tracks = []

    def update(self, things, dt, player_xy, max_move, new_bullet_speed):
        """things: [vision.Thing]. max_move: the fastest anything moves (px/s), to match between frames.
        A new bullet gets a guessed speed: flying away from the boss / yellow mob next to it (their rings)
        or else straight at the player (shooters aim at you)."""
        px, py = player_xy if player_xy else (None, None)
        out = []
        for kind in KINDS:
            old = [t for t in self.tracks if t.kind == kind]
            new = [t for t in things if t.kind == kind]
            pairs = []
            for j, n in enumerate(new):
                limit = max_move * dt + n.r + 8
                for i, t in enumerate(old):
                    d = math.hypot(t.x + t.vx * dt - n.x, t.y + t.vy * dt - n.y)
                    if d < limit:
                        pairs.append((d, i, j))
            pairs.sort()
            used, matched = set(), {}
            for d, i, j in pairs:  # closest pairs first, so dense bullet rings don't swap tracks
                if i not in used and j not in matched:
                    used.add(i)
                    matched[j] = i
            for j, n in enumerate(new):
                if j in matched:
                    t = old[matched[j]]
                    mvx, mvy = (n.x - t.x) / dt, (n.y - t.y) / dt
                    a = 1.0 if t.age == 0 else 0.5  # first real measurement replaces the guess
                    t.vx, t.vy = (1 - a) * t.vx + a * mvx, (1 - a) * t.vy + a * mvy
                    t.x, t.y, t.r = n.x, n.y, n.r
                    t.vmax = max(t.speed, t.vmax * 0.995)
                    t.age += 1
                    t.missing = 0
                    out.append(t)
                else:
                    vx = vy = 0.0
                    if kind == "bullet":
                        src = min((s for s in self.tracks if s.kind in ("boss", "yellow")
                                   and math.hypot(s.x - n.x, s.y - n.y) < s.r * 2.2), default=None,
                                  key=lambda s: math.hypot(s.x - n.x, s.y - n.y))
                        if src is not None:
                            ox, oy = n.x - src.x, n.y - src.y
                        elif px is not None:
                            ox, oy = px - n.x, py - n.y
                        else:
                            ox = oy = 0.0
                        d = math.hypot(ox, oy) or 1.0
                        vx, vy = ox / d * new_bullet_speed, oy / d * new_bullet_speed
                    out.append(Track(kind, n.x, n.y, n.r, vx, vy))
            # keep things that vanished for a frame or two (flicker, overlap) at their predicted spot
            for i, t in enumerate(old):
                if i not in used and t.missing < 2:
                    t.missing += 1
                    t.x += t.vx * dt
                    t.y += t.vy * dt
                    out.append(t)
        self.tracks = out
        return out
