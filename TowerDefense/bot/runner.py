"""
The bot loop, independent of Windows: grab a frame -> find things -> decide -> send input.
`swarm_bot.py` plugs in the real screen/keyboard/mouse; the tests plug in a browser.
"""

import math

from brain import DEFAULT_PLAYER_SPEED, REF_R, Brain
from vision import Detector, Tracker


class BotRunner:
    def __init__(self, cfg, io, params=None):
        self.cfg = cfg
        self.io = io
        # Dodge settings trained in the simulator (config "brain_params"), or the defaults.
        self.params = params if params is not None else cfg.get("brain_params")
        self.detector = Detector(cfg)
        # The player blinks when hit and banners cover the screen, so only give up after a while.
        self.death_timeout = max(3.0, float(cfg.get("death_timeout", 4.0)))
        self.player_radius = float((cfg.get("colors", {}).get("player") or {}).get("radius", 0)) or None
        self.reset()

    def reset(self):
        self.tracker = Tracker()
        self.brain = Brain(bullet_speed=float(self.cfg.get("bullet_speed", 820)), params=self.params)
        self.player = None
        self.player_speed = None  # measured, in screen pixels per second
        self.last_keys = ()
        self.missing_time = 0.0
        self.seen_player = False
        self.last_t = None
        self.stuck_time = 0.0
        self.latency = 0.05  # seconds from screenshot to keys, measured while running
        self.bad_spots = []  # [(x, y, until_time)]: static things mistaken for the player
        self.notes = []      # messages for the log, collected by the caller
        self.last = None     # everything from the latest tick, for screenshots
        self.first_seen = None  # time the player was first seen this run
        self.last_seen = None
        self.started = None     # time of the first tick

    def run_seconds(self):
        """How long the player survived this run (first to last sighting)."""
        if self.first_seen is None:
            return 0.0
        return self.last_seen - self.first_seen

    def waiting_time(self):
        """Seconds since the bot started without ever seeing the player."""
        if self.seen_player or self.started is None:
            return 0.0
        return self.io.now() - self.started

    def release(self):
        self.io.set_keys(())
        self.io.mouse(False)
        self.last_keys = ()

    def _pick_player(self, candidates, now):
        """Which gray blob is the player. Returns (x, y, r) or None."""
        if not candidates:
            return None
        self.bad_spots = [b for b in self.bad_spots if b[2] > now]
        good = [c for c in candidates
                if not any(math.hypot(c[0] - bx, c[1] - by) < c[2] + 4 for bx, by, _ in self.bad_spots)]
        if not good:
            # Everything player-sized is blacklisted: the blacklist was wrong, drop it.
            self.bad_spots = []
            good = candidates
        by_size = (lambda b: abs(math.log(max(b[2], 0.5) / self.player_radius))) if self.player_radius \
            else (lambda b: -b[2])
        if self.player is None:
            return min(good, key=by_size)
        # Follow the blob closest to where the player was.
        px, py, pr = self.player
        best = min(good, key=lambda b: math.hypot(b[0] - px, b[1] - py))
        if math.hypot(best[0] - px, best[1] - py) <= 6 * max(pr, 1) + 50:
            return best
        # Nothing near the old spot. After a short blink (hit flash), look for it anywhere.
        if self.missing_time > 0.2:
            return min(good, key=by_size)
        return None

    def step(self):
        """One tick. Returns "ok", "waiting" (player not seen yet) or "dead"."""
        now = self.io.now()
        if self.started is None:
            self.started = now
        dt = 1 / 30 if self.last_t is None else max(1e-3, min(0.2, now - self.last_t))
        self.last_t = now

        frame = self.io.grab()
        # When the screenshot was taken (the capture thread knows exactly), else "now".
        t_grab = getattr(self.io, "frame_time", 0.0) or self.io.now()
        h, w = frame.shape[:2]
        dets = self.detector.detect(frame)
        found = self._pick_player(dets["player"], now)
        self.last = {"frame": frame, "dets": dets, "player": found, "keys": self.last_keys, "aim": None, "fire": False}
        estimated = False
        if found is None:
            self.missing_time += dt
            if self.seen_player and self.missing_time > self.death_timeout:
                self.release()
                return "dead"
            if self.player is None or self.missing_time > 1.5:
                return "waiting" if not self.seen_player else "ok"
            # Can't see the player right now (behind a mob or a HUD panel): keep playing from where
            # it should be, based on the keys being held, instead of freezing.
            px, py, pr = self.player
            dx = ("d" in self.last_keys) - ("a" in self.last_keys)
            dy = ("s" in self.last_keys) - ("w" in self.last_keys)
            norm = math.hypot(dx, dy) or 1.0
            spd = self.player_speed or DEFAULT_PLAYER_SPEED * pr / REF_R
            found = (min(max(px + dx / norm * spd * dt, pr), w - pr), min(max(py + dy / norm * spd * dt, pr), h - pr), pr)
            self.last["player"] = found
            estimated = True
        else:
            self.missing_time = 0.0
            self.seen_player = True
            if self.first_seen is None:
                self.first_seen = now
            self.last_seen = now
        x, y, r = found

        if self.player is not None and self.last_keys and not estimated:
            moved = math.hypot(x - self.player[0], y - self.player[1]) / dt
            # Measure the player's real speed from how far it moved while a direction was held.
            diag = len(self.last_keys) == 2
            blocked = self.player_speed is not None and moved < 0.5 * self.player_speed  # against a wall
            if 0 < moved < r / REF_R * 1000 and not diag and not blocked:
                self.player_speed = moved if self.player_speed is None else 0.9 * self.player_speed + 0.1 * moved
            # Holding keys but "the player" doesn't move and isn't at a wall: it's probably
            # something static (HUD text, a button). Forget it and look for the real one.
            near_wall = min(x, w - x, y, h - y) < 3 * r
            # Only when there's another candidate: if it's the only gray ball it IS the player
            # (just pinned, e.g. by the boss), and ignoring it would make the bot think it died.
            alternatives = len(dets["player"]) > 1
            self.stuck_time = self.stuck_time + dt if (moved < r * 0.5 and not near_wall and alternatives) else 0.0
            if self.stuck_time > 1.0:
                self.bad_spots.append((x, y, now + 8))
                self.notes.append(f"Player not moving at ({x:.0f}, {y:.0f}); probably not the player, looking again.")
                self.player = None
                self.stuck_time = 0.0
                self.release()
                return "ok"
        self.player = (x, y, r)
        speed = self.player_speed or DEFAULT_PLAYER_SPEED * r / REF_R

        k = r / REF_R
        tracks = self.tracker.update(dets, dt, (x, y), max_speed=400 * k, new_bullet_speed=260 * k)
        # Delay between the screenshot and our keys taking effect (processing + roughly one frame).
        keys, aim, fire = self.brain.think((x, y, r), speed, tracks, w, h, latency=min(0.25, self.latency))
        self.last.update({"keys": keys, "aim": aim, "fire": fire, "speed": speed, "t": t_grab,
                          # moving things with their speed, so the overlay can glide between frames
                          "tracks": [(tr.kind, tr.x, tr.y, tr.r, tr.vx, tr.vy) for tr in tracks]})

        if not self.io.focused():
            self.release()
            return "ok"
        if keys != self.last_keys:
            self.io.set_keys(keys)
            self.last_keys = keys
        if aim is not None:
            self.io.aim(min(max(aim[0], 0), w - 1), min(max(aim[1], 0), h - 1))
        self.io.mouse(fire)
        self.latency = 0.8 * self.latency + 0.2 * max(0.0, self.io.now() - t_grab + dt * 0.5)
        return "ok"
