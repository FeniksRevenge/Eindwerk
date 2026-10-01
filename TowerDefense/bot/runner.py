"""
The bot loop, independent of Windows: grab a frame -> find things -> decide -> send input.
`swarm_bot.py` plugs in the real screen/keyboard/mouse; the tests plug in a browser.
"""

import math

import cv2
import numpy as np

from brain import DEFAULT_PLAYER_SPEED, REF_R, Brain
from vision import Detector, Tracker, is_game_over

HOLD_MAX = 15.0  # seconds it keeps you at a spot by your picture alone, without recognizing you


class BotRunner:
    def __init__(self, cfg, io, params=None):
        self.cfg = cfg
        self.io = io
        # Dodge settings trained in the simulator (config "brain_params"), or the defaults.
        self.params = params if params is not None else cfg.get("brain_params")
        self.detector = Detector(cfg)
        # Death = the GAME OVER screen. Not seeing the player only counts as death after a long time
        # (backup, in case the game-over screen looks different on your PC).
        self.death_timeout = max(20.0, float(cfg.get("death_timeout", 30.0)))
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
        self.game_over_since = None
        self.death_reason = ""
        self.template = None    # small gray picture of the player, from the last time it was recognized
        self.hold_time = 0.0    # how long it's been kept at its spot by that picture alone
        self.lost_report = False  # set once per run when the player is lost for 1 s (for a screenshot)
        self.lost_reported = False
        self.frames = 0

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

    def _save_template(self, frame, found):
        x, y, r = found
        h = int(max(6, 1.4 * r))
        x0, y0 = int(x) - h, int(y) - h
        if x0 < 0 or y0 < 0 or x0 + 2 * h > frame.shape[1] or y0 + 2 * h > frame.shape[0]:
            return
        patch = cv2.cvtColor(np.ascontiguousarray(frame[y0:y0 + 2 * h, x0:x0 + 2 * h]), cv2.COLOR_BGR2GRAY)
        if patch.std() > 8:  # has the player in it (not a flat patch)
            self.template = (patch, (x, y, r))

    def _match_template(self, frame):
        """Where the player's last picture is, near its last spot, or None."""
        patch, (tx, ty, r) = self.template
        th = patch.shape[0] // 2
        reach = int(max(4, 0.6 * r))
        x0, y0 = int(tx) - th - reach, int(ty) - th - reach
        x1, y1 = int(tx) + th + reach, int(ty) + th + reach
        if x0 < 0 or y0 < 0 or x1 > frame.shape[1] or y1 > frame.shape[0]:
            return None
        win = cv2.cvtColor(np.ascontiguousarray(frame[y0:y1, x0:x1]), cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(win, patch, cv2.TM_CCOEFF_NORMED)
        _, best, _, (bx, by) = cv2.minMaxLoc(res)
        if best < 0.8:
            return None
        return (x0 + bx + th, y0 + by + th, r)

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
        self.frames += 1
        # The GAME OVER screen means dead (checked every frame while the player is missing, else now and then).
        if found is None or self.frames % 10 == 0:
            if is_game_over(frame):
                if self.game_over_since is None:
                    self.game_over_since = now
                if self.seen_player and now - self.game_over_since >= 0.4:
                    self.release()
                    self.death_reason = "game over screen"
                    return "dead"
            else:
                self.game_over_since = None
        held = False
        if found is None and self.template is not None and self.player is not None and self.hold_time < HOLD_MAX:
            # Not recognized, but is the player still right there (e.g. standing still)? Compare with
            # its picture from the last time it was recognized.
            found = self._match_template(frame)
            if found is not None:
                held = True
                self.hold_time += dt
        self.last = {"frame": frame, "dets": dets, "player": found, "keys": self.last_keys, "aim": None, "fire": False}
        estimated = False
        if found is None:
            self.missing_time += dt
            if self.seen_player and self.missing_time > 1.0 and not self.lost_reported:
                self.lost_report = self.lost_reported = True  # the controller saves a screenshot
            if self.seen_player and self.missing_time > self.death_timeout:
                self.release()
                self.death_reason = f"couldn't see the player for {self.death_timeout:.0f} s"
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
            if not held:
                self.hold_time = 0.0
                self._save_template(frame, found)
            estimated = held  # no speed measuring / stuck check on a held position
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
