"""
The bot loop, independent of Windows: grab a frame -> find things -> decide -> send input.
`swarm_bot.py` plugs in the real screen/keyboard/mouse; the tests plug in a browser.
"""

import math

from brain import DEFAULT_PLAYER_SPEED, REF_R, Brain
from vision import Detector, Tracker


class BotRunner:
    def __init__(self, cfg, io):
        self.cfg = cfg
        self.io = io
        self.detector = Detector(cfg)
        self.death_timeout = float(cfg.get("death_timeout", 1.0))
        self.reset()

    def reset(self):
        self.tracker = Tracker()
        self.brain = Brain(bullet_speed=float(self.cfg.get("bullet_speed", 820)))
        self.player = None
        self.player_speed = None  # measured, in screen pixels per second
        self.last_keys = ()
        self.missing_time = 0.0
        self.seen_player = False
        self.last_t = None

    def release(self):
        self.io.set_keys(())
        self.io.mouse(False)
        self.last_keys = ()

    def step(self):
        """One tick. Returns "ok", "waiting" (player not seen yet) or "dead"."""
        now = self.io.now()
        dt = 1 / 30 if self.last_t is None else max(1e-3, min(0.2, now - self.last_t))
        self.last_t = now

        frame = self.io.grab()
        dets = self.detector.detect(frame)
        players = dets["player"]
        if self.player is not None:
            # Follow the blob closest to where the player was, so gray HUD text can't steal it.
            px, py = self.player[0], self.player[1]
            players = sorted(players, key=lambda b: math.hypot(b[0] - px, b[1] - py))
            if players and math.hypot(players[0][0] - px, players[0][1] - py) > 6 * max(self.player[2], 1) + 50:
                players = []
        else:
            players = sorted(players, key=lambda b: -b[2])
        if not players:
            self.missing_time += dt
            if self.seen_player and self.missing_time > self.death_timeout:
                self.release()
                return "dead"
            return "waiting" if not self.seen_player else "ok"
        self.missing_time = 0.0
        self.seen_player = True
        x, y, r = players[0]

        # Measure the player's real speed from how far it moved while a direction was held.
        if self.player is not None and self.last_keys:
            moved = math.hypot(x - self.player[0], y - self.player[1]) / dt
            diag = len(self.last_keys) == 2
            blocked = self.player_speed is not None and moved < 0.5 * self.player_speed  # against a wall
            if 0 < moved < r / REF_R * 1000 and not diag and not blocked:
                self.player_speed = moved if self.player_speed is None else 0.9 * self.player_speed + 0.1 * moved
        self.player = (x, y, r)
        speed = self.player_speed or DEFAULT_PLAYER_SPEED * r / REF_R

        k = r / REF_R
        tracks = self.tracker.update(dets, dt, (x, y), max_speed=400 * k, new_bullet_speed=260 * k)
        h, w = frame.shape[:2]
        keys, aim, fire = self.brain.think((x, y, r), speed, tracks, w, h)

        if not self.io.focused():
            self.release()
            return "ok"
        if keys != self.last_keys:
            self.io.set_keys(keys)
            self.last_keys = keys
        if aim is not None:
            self.io.aim(min(max(aim[0], 0), w - 1), min(max(aim[1], 0), h - 1))
        self.io.mouse(fire)
        return "ok"
