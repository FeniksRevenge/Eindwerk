"""
The bot loop: screenshot -> see -> follow -> decide -> keys and mouse. Platform independent: `io` is the
Windows side (winio.WindowsIO) in the app, or a fake game in the tests.

io must have: grab() -> frame or None, frame_time, now(), focused(), set_keys(names), fire(on),
aim(x, y), click(x, y), release().
"""

import collections
import math
import time

import cv2
import numpy as np

from planner import Planner
from tracker import Tracker
from vision import REF_H, Detector, annotate, find_play_again, game_over_info, is_game_over

HOLD_MAX = 15.0       # seconds it may keep you at a spot by your picture alone
RECORD_SECONDS = 8.0  # how much the "record" key saves


class BotRunner:
    def __init__(self, io, auto_restart=False, log=lambda text: None):
        self.io = io
        self.auto_restart = auto_restart
        self.log = log
        self.detector = Detector()
        self.planner = Planner()
        self.recording = collections.deque()
        self.reset_run()
        self.input_delay = 0.08   # seconds from sending keys until you visibly move (measured while playing)
        self.player_speed = None  # pixels per second (measured while playing)

    def reset_run(self):
        self.tracker = Tracker()
        self.player = None
        self.seen = False
        self.missing = 0.0
        self.hold = 0.0
        self.template = None
        self.keys = ()
        self.key_log = [(-1e9, ())]
        self.motion = []
        self.next_delay_check = 0.0
        self.last_t = None
        self.latency = 0.03
        self.game_over_since = None
        self.restart = None   # auto restart in progress: {"since", "clicks", "last_click"}
        self.started = self.first_seen = self.last_seen = None
        self.last = None      # everything from the latest step (screenshots, recordings)

    def run_seconds(self):
        return 0.0 if self.first_seen is None else self.last_seen - self.first_seen

    def release(self):
        self.io.release()
        self.keys = ()

    # ------------------------------------------------------------------ one step
    def step(self):
        """Returns "playing", "waiting" (you're not visible yet), "no_window", "restarting" or "dead"."""
        frame = self.io.grab()
        now = self.io.now()
        if frame is None:
            self.release()
            return "no_window"
        t_grab = getattr(self.io, "frame_time", 0.0) or now
        dt = 1 / 30 if self.last_t is None else max(1e-3, min(0.2, now - self.last_t))
        self.last_t = now
        if self.started is None:
            self.started = now
        H, W = frame.shape[:2]

        # --- game over / auto restart
        if is_game_over(frame):
            self.release()
            self.last = {"frame": frame, "player": None, "things": [], "keys": (), "aim": None, "t": t_grab,
                         "note": "GAME OVER screen"}
            self._record()
            if self.game_over_since is None:
                self.game_over_since = now
            if not self.seen and self.restart is None:
                return "waiting"
            if now - self.game_over_since < 0.4:
                return "playing"
            if not self.auto_restart:
                return "dead"
            return self._auto_restart(frame, now)
        self.game_over_since = None
        if self.restart is not None and self.restart["clicks"]:
            # the GAME OVER screen is gone after our click: a new game (after its countdown)
            secs = self.restart["secs"]
            self.reset_run()
            self.started = now
            self.log(f"Auto restart: new game started (last one lasted {secs:.0f} s).")

        player, things = self.detector.detect(frame)
        held = False
        if player is None and self.template is not None and self.player is not None and self.hold < HOLD_MAX:
            player = self._match_template(frame)  # not recognized, but still right there?
            held = player is not None
        if player is None:
            self.missing += dt
            self.last = {"frame": frame, "player": None, "things": things, "keys": self.keys, "aim": None,
                         "t": t_grab, "note": "can't see you"}
            self._record()
            if self.player is None or self.missing > 1.0:
                if self.seen:
                    self.release()  # don't run blindly into things
                return "waiting" if not self.seen else "playing"
            # lost for a moment (behind something): keep going from where you should be
            x, y = self._replay(self.player[0], self.player[1], now - dt, now)
            player = (x, y, self.player[2])
        else:
            self.missing = 0.0
            if held:
                self.hold += dt
            else:
                self.hold = 0.0
                self._save_template(frame, player)
                self.motion.append((t_grab, player[0], player[1]))
                del self.motion[:-150]
            if not self.seen:
                self.seen = True
                self.first_seen = now
            self.last_seen = now
        x, y, R = player
        self._measure_speed(W, H, R, held)
        self.player = player
        V = self.player_speed or 0.5 * H
        if now >= self.next_delay_check:
            self.next_delay_check = now + 0.5
            self._measure_input_delay(V, R, W, H)

        tracks = self.tracker.update(things, dt, (x, y), max_move=1.6 * H, new_bullet_speed=0.6 * H)
        # where you'll be when new keys take effect: the screenshot shows the keys from input_delay ago,
        # the keys sent since then are still on their way
        lat = min(0.45, self.latency + self.input_delay)
        sx, sy = self._replay(x, y, t_grab - self.input_delay, now, V)
        keys, aim = self.planner.plan((x, y, R), V, tracks, W, H, latency=lat, start=(sx, sy))

        self.last = {"frame": frame, "player": player, "things": things, "keys": keys, "aim": aim, "t": t_grab,
                     "speed": V, "delay": lat, "note": "held" if held else ""}
        self._record()
        if not self.io.focused():
            self.release()
            return "playing"
        if keys != self.keys:
            self.io.set_keys(keys)
            self.keys = keys
            self.key_log.append((now, keys))
            del self.key_log[1:-200]
        if aim is not None:
            self.io.aim(min(max(aim[0], 0), W - 1), min(max(aim[1], 0), H - 1))
        self.io.fire(True)
        self.latency = 0.8 * self.latency + 0.2 * max(0.0, self.io.now() - t_grab)
        return "playing"

    def _auto_restart(self, frame, now):
        r = self.restart
        if r is None:
            r = self.restart = {"since": now, "clicks": 0, "last_click": 0.0, "secs": self.run_seconds()}
            self.log(f"Game over after {r['secs']:.0f} s. Auto restart: clicking PLAY AGAIN.")
        if now - r["since"] < 1.0 or now - r["last_click"] < 3.0:
            return "restarting"  # let the screen finish appearing / give the last click time to work
        if r["clicks"] >= 3:
            info = game_over_info(frame)
            self.log(f"Auto restart failed: clicked PLAY AGAIN 3 times but the GAME OVER screen stayed "
                     f"(background {info['border']}, middle {info['middle']}). Stopped.")
            self.restart = None
            return "dead"
        pos = find_play_again(frame)
        if pos is None or not self.io.focused():
            return "restarting"
        self.io.click(*pos)
        r["clicks"] += 1
        r["last_click"] = now
        return "restarting"

    # ------------------------------------------------------------------ measuring yourself
    def _measure_speed(self, W, H, R, held):
        """Your walking speed, from how far you moved while one direction was held for a while."""
        if held or len(self.motion) < 2 or not self.keys:
            return
        (t0, x0, y0), (t1, x1, y1) = self.motion[-2], self.motion[-1]
        if not (0 < t1 - t0 < 0.15) or self.io.now() - self.key_log[-1][0] < self.input_delay + 0.1:
            return
        if min(x1, y1, W - x1, H - y1) < 2.5 * R:
            return  # at a wall
        v = math.hypot(x1 - x0, y1 - y0) / (t1 - t0)
        if 0.15 * H < v < 1.5 * H:
            self.player_speed = v if self.player_speed is None else 0.9 * self.player_speed + 0.1 * v

    def _replay(self, x, y, t_from, t_to, speed=None):
        """Where the keys sent between t_from and t_to move you from (x, y)."""
        speed = speed or self.player_speed or 0.0
        log = self.key_log
        for i, (ts, keys) in enumerate(log):
            te = log[i + 1][0] if i + 1 < len(log) else t_to
            a, b = max(ts, t_from), min(te, t_to)
            if b <= a or not keys:
                continue
            dx = ("right" in keys) - ("left" in keys)
            dy = ("down" in keys) - ("up" in keys)
            n = math.hypot(dx, dy) or 1.0
            x += dx / n * speed * (b - a)
            y += dy / n * speed * (b - a)
        return x, y

    def _keys_at(self, t):
        keys = ()
        for ts, k in self.key_log:
            if ts > t:
                break
            keys = k
        return keys

    def _measure_input_delay(self, speed, R, W, H):
        """Which delay best explains how you moved after each key change (0 .. 0.4 s)?"""
        m = self.motion[-90:]
        if len(m) < 20 or len(self.key_log) < 4:
            return
        pairs = []
        for (t0, x0, y0), (t1, x1, y1) in zip(m, m[1:]):
            if 0 < t1 - t0 < 0.15 and min(x0, y0, W - x0, H - y0, x1, y1, W - x1, H - y1) >= 2.5 * R:
                pairs.append(((t0 + t1) / 2, (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)))
        if len(pairs) < 15:
            return
        errs = []
        for d in np.arange(0.0, 0.42, 0.02):
            e = 0.0
            for tm, vx, vy in pairs:
                keys = self._keys_at(tm - d)
                dx = ("right" in keys) - ("left" in keys)
                dy = ("down" in keys) - ("up" in keys)
                n = math.hypot(dx, dy) or 1.0
                e += (vx - dx / n * speed) ** 2 + (vy - dy / n * speed) ** 2
            errs.append(e)
        best = int(np.argmin(errs))
        if errs[best] < 0.85 * max(errs):
            self.input_delay = 0.7 * self.input_delay + 0.3 * float(best * 0.02)

    # ------------------------------------------------------------------ "is it still you?"
    def _save_template(self, frame, player):
        x, y, r = player
        h = int(max(8, 1.3 * r))
        x0, y0 = int(x) - h, int(y) - h
        if x0 < 0 or y0 < 0 or x0 + 2 * h > frame.shape[1] or y0 + 2 * h > frame.shape[0]:
            return
        patch = cv2.cvtColor(np.ascontiguousarray(frame[y0:y0 + 2 * h, x0:x0 + 2 * h]), cv2.COLOR_BGR2GRAY)
        if patch.std() > 8:
            self.template = (patch, (x, y, r))

    def _match_template(self, frame):
        patch, (tx, ty, r) = self.template
        th = patch.shape[0] // 2
        reach = int(max(4, 0.6 * r))
        x0, y0, x1, y1 = int(tx) - th - reach, int(ty) - th - reach, int(tx) + th + reach, int(ty) + th + reach
        if x0 < 0 or y0 < 0 or x1 > frame.shape[1] or y1 > frame.shape[0]:
            return None
        win = cv2.cvtColor(np.ascontiguousarray(frame[y0:y1, x0:x1]), cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(win, patch, cv2.TM_CCOEFF_NORMED)
        _, best, _, (bx, by) = cv2.minMaxLoc(res)
        return (x0 + bx + th, y0 + by + th, r) if best >= 0.8 else None

    # ------------------------------------------------------------------ pictures for you to send
    def _record(self):
        """Keep the last few seconds (small pictures + what it saw and did), for the record key."""
        last = self.last
        if last is None:
            return
        t = last["t"]
        if self.recording and t - self.recording[-1][0] < 1 / 15:
            return
        small = cv2.resize(last["frame"], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        info = {"t": round(t, 3), "player": last["player"] and [round(v, 1) for v in last["player"]],
                "keys": list(last["keys"]), "aim": last["aim"] and [round(v) for v in last["aim"]],
                "things": [[th.kind, round(th.x), round(th.y), round(th.r)] for th in last["things"]],
                "speed": round(last.get("speed", 0) or 0), "delay": round(last.get("delay", 0) or 0, 3),
                "note": last.get("note", "")}
        self.recording.append((t, jpg.tobytes() if ok else b"", info))
        while self.recording and t - self.recording[0][0] > RECORD_SECONDS:
            self.recording.popleft()

    def picture(self):
        """The latest screenshot with everything it sees drawn on it (for the screenshot key)."""
        last = self.last
        if last is None:
            return None, None
        text = f"speed {last.get('speed', 0) or 0:.0f}px/s  delay {1000 * (last.get('delay', 0) or 0):.0f}ms  {last.get('note', '')}"
        return last["frame"], annotate(last["frame"], last["player"], last["things"], last["keys"], last["aim"], text)


def now_stamp():
    return time.strftime("%Y%m%d_%H%M%S")
