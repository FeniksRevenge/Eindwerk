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

from planner import BODY_BACK, MOB_SPEED, Planner, body_reach
from tracker import Tracker
from vision import REF_H, Detector, annotate, find_leave, game_over_info, is_game_over, HPBar

HOLD_MAX = 15.0       # seconds it may keep you at a spot by your picture alone
RECORD_SECONDS = 8.0  # how much the "record" key saves
LOST_STILL = 45.0     # the picture hasn't changed for this long: frozen / disconnected
LOST_MISSING = 90.0   # you've been gone this long without a GAME OVER screen: not in the game anymore
LOST_WAITING = 150.0  # after an auto restart, no new game within this long
LOST_NO_WINDOW = 60.0
E_AFTER_LEAVE = 2.0   # after LEAVE: wait this long, then press E (you stand at the arcade machine)
E_RETRY = 8.0         # no game yet this long after E: press it again (at most E_TRIES times)
E_TRIES = 4


class BotRunner:
    def __init__(self, io, auto_restart=False, log=lambda text: None, learner=None):
        self.io = io
        self.auto_restart = auto_restart
        self.log = log
        self.learner = learner
        self.events = []      # ("hit", cause) for the app (it saves a clip of every hit)
        self.detector = Detector()
        self.planner = Planner()
        self.recording = collections.deque()
        self.after_restart = None   # when the last auto restart click worked
        self.lobby = None           # after LEAVE: {"left", "e", "last_e"} until the game is back
        self.no_window_since = None
        self.reset_run()
        if not getattr(self, "_me_loaded", False):
            self.input_delay = 0.08   # seconds from sending keys until you visibly move (measured while playing)
        self.player_speed = None  # pixels per second (measured while playing)
        self.H = None

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
        self.hp = None        # last trusted HP reading (0..1)
        self.hp_reads = []
        self.hp_change = None   # when the HP bar first looked different (the hit's time)
        self.hp_bar = HPBar()
        self.history = collections.deque()   # (t, (x, y, R), things) of the last second, to see what hit you
        self.still = (None, 0.0, 0.0)          # (small picture, when, how long it hasn't changed)
        self.run_over = False
        if self.learner is not None:
            self.planner.room = self.learner.room
            self.planner.mob_speed = dict(MOB_SPEED, **self.learner.speed)
            self.planner.style = self.learner.current_style()
            self.planner.body_scale = self.learner.body_scale()
            if self.learner.me.get("delay") is not None and not getattr(self, "_me_loaded", False):
                self.input_delay = min(0.4, max(0.0, self.learner.me["delay"]))
                self._me_loaded = True
        self.aim_pt = None

    def run_seconds(self):
        return 0.0 if self.first_seen is None else self.last_seen - self.first_seen

    def release(self):
        self.io.release()
        self.keys = ()

    # ------------------------------------------------------------------ one step
    def step(self):
        """Returns "playing", "waiting" (you're not visible yet), "no_window", "restarting" or "dead"."""
        t0 = time.perf_counter()
        frame = self.io.grab()
        now = self.io.now()
        self.ms = {"grab": round(1000 * (time.perf_counter() - t0), 1)}
        if frame is None:
            self.release()
            if self.no_window_since is None:
                self.no_window_since = now
            if now - self.no_window_since > LOST_NO_WINDOW and (self.seen or self.after_restart):
                return self._lost(f"the Roblox window was gone for {LOST_NO_WINDOW:.0f} s")
            return "no_window"
        self.no_window_since = None
        t_grab = getattr(self.io, "frame_time", 0.0) or now
        dt = 1 / 30 if self.last_t is None else max(1e-3, min(0.2, now - self.last_t))
        self.last_t = now
        if self.started is None:
            self.started = now
        H, W = frame.shape[:2]
        self.H = H
        if self.player_speed is None and self.learner is not None and self.learner.me.get("speed"):
            self.player_speed = self.learner.me["speed"] * H  # last runs' measurement, until measured again
        if (self.seen or self.after_restart) and self._frozen(frame, now):
            return self._lost(f"the picture hasn't changed for {LOST_STILL:.0f} s")

        # --- game over / auto restart
        if is_game_over(frame):
            self._end_run("game over")
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
            # the GAME OVER screen is gone after clicking LEAVE: you're back next to the arcade machine
            secs = self.restart["secs"]
            self.reset_run()
            self.started = now
            self.after_restart = now
            self.lobby = {"left": now, "e": 0, "last_e": 0.0}
            self.log(f"Left the game (it lasted {secs:.0f} s). Pressing E in {E_AFTER_LEAVE:.0f} s to start it again.")
        if not self.seen and self.after_restart is not None and now - self.after_restart > LOST_WAITING:
            return self._lost(f"no new game {LOST_WAITING:.0f} s after leaving and pressing E")
        if self.lobby is not None:
            if self.lobby["e"] and self.hp_bar.read(frame[::2, ::2]) is not None:
                self.lobby = None  # the game's HUD is back: play (after its countdown)
                self.log("New game started.")
            else:
                return self._press_e(now)

        t1 = time.perf_counter()
        player, things = self.detector.detect(frame)
        self.ms["detect"] = round(1000 * (time.perf_counter() - t1), 1)
        held = False
        if player is None and self.template is not None and self.player is not None and self.hold < HOLD_MAX:
            player = self._match_template(frame)  # not recognized, but still right there?
            held = player is not None
        if player is None:
            self.missing += dt
            self.last = {"frame": frame, "player": None, "things": things, "keys": self.keys, "aim": None,
                         "t": t_grab, "note": "can't see you"}
            self._record()
            if self.seen and self.missing > LOST_MISSING:
                return self._lost(f"you weren't visible for {LOST_MISSING:.0f} s and there was no GAME OVER screen")
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

        bs = {"": 0.6 * H}
        if self.learner is not None:
            bs.update({c: v * H for c, v in self.learner.bullet_speed.items()})
        tracks = self.tracker.update(things, dt, (x, y), max_move=1.6 * H, new_bullet_speed=bs)
        self._watch_hp(frame, now, (x, y, R), things)
        if self.learner is not None:
            self.learner.played(dt, tracks, V, H)
        # where you'll be when new keys take effect: the screenshot shows the keys from input_delay ago,
        # the keys sent since then are still on their way
        lat = min(0.45, self.latency + self.input_delay)
        sx, sy = self._replay(x, y, t_grab - self.input_delay, now, V)
        t1 = time.perf_counter()
        keys, aim = self.planner.plan((x, y, R), V, tracks, W, H, latency=lat, start=(sx, sy))
        self.ms["plan"] = round(1000 * (time.perf_counter() - t1), 1)

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
        self.aim_pt = aim
        if aim is not None:
            self.io.aim(min(max(aim[0], 0), W - 1), min(max(aim[1], 0), H - 1))
        self.io.fire(True)
        self.latency = 0.8 * self.latency + 0.2 * max(0.0, self.io.now() - t_grab)
        return "playing"

    # ------------------------------------------------------------------ learning, and noticing trouble
    def _watch_hp(self, frame, now, me, things):
        """Reads the HP bar; when it drops, works out what hit you (the closest thing just before)."""
        face = None
        if self.aim_pt is not None:  # the UFO faces the mouse
            fx, fy = self.aim_pt[0] - me[0], self.aim_pt[1] - me[1]
            fn = math.hypot(fx, fy)
            face = (fx / fn, fy / fn) if fn > 1 else None
        self.history.append((now, me, [(th.kind, th.x, th.y, th.r) for th in things], face))
        while self.history and now - self.history[0][0] > 1.6:
            self.history.popleft()
        small = frame[::16, ::16]
        if np.median(small[..., 2]) > max(30, 2 * np.median(small[..., 0])):
            self.hp_reads = []  # the screen flashes red right after a hit: the bar can't be read
            if self.hp_change is None:
                self.hp_change = now  # (when the hit happened: the bar takes a few pictures to trust)
            return
        v = self.hp_bar.read(frame[::2, ::2])
        if v is None:
            return
        if self.hp is not None and v < self.hp - 0.05 and self.hp_change is None:
            self.hp_change = now
        self.hp_reads = (self.hp_reads + [v])[-4:]
        if len(self.hp_reads) < 4 or max(self.hp_reads) - min(self.hp_reads) > 0.03:
            return
        v = sum(self.hp_reads) / 4
        t_hit, self.hp_change = (self.hp_change or now), None
        if self.hp is not None and v < self.hp - 0.05:
            cause = self._what_hit(t_hit)
            self.events.append(("hit", cause))
            if self.learner is not None:
                self.learner.hit(cause)
                fit = self._body_fit(t_hit, cause)
                if fit is not None:
                    self.learner.body_fit(fit)
            self.log(f"Hit by {cause} (HP {10 * v:.0f}/10).")
        self.hp = v

    def _what_hit(self, now):
        best, cause = None, "unknown"
        for t, (x, y, R), things, _ in self.history:
            if not -0.6 <= t - now <= 0.05:
                continue
            for kind, tx, ty, tr in things:
                if kind in ("health", "spawn"):
                    continue
                g = (math.hypot(tx - x, ty - y) - 1.2 * R - tr) / R
                if best is None or g < best:
                    best, cause = g, kind
        return cause if best is not None and best < 2.5 else "unknown"

    def _body_fit(self, now, cause):
        """How big your body must have been (x the UFO shape) to just touch the thing that hit you:
        the closest it came to you in the last moments, between screenshots too (things move a lot
        from one screenshot to the next)."""
        if cause not in ("bullet", "grunt", "tiny", "yellow", "shooter"):
            return None  # (only small, round-ish things: the boss's and tanks' outlines are too rough)
        h = [e for e in self.history if -0.6 <= e[0] - now <= 0.05 and e[3] is not None]
        best = None
        for (ta, ma, tha, fa), (tb, mb, thb, _) in zip(h, h[1:]):
            R = ma[2]
            face = np.array(fa)
            ca = np.array(ma[:2]) - face * BODY_BACK * R
            cb = np.array(mb[:2]) - face * BODY_BACK * R
            lim = 1.6 * (self.H or 1000) * (tb - ta) + 3 * R
            for kind, x, y, r in tha:
                if kind != cause:
                    continue
                nxt = min(((math.hypot(x2 - x, y2 - y), x2, y2) for k2, x2, y2, r2 in thb if k2 == kind),
                          default=None)
                ra = np.array([x, y]) - ca
                rb = (np.array(nxt[1:]) - cb) if nxt is not None and nxt[0] < lim else ra
                seg = rb - ra
                u = min(1.0, max(0.0, -float(ra @ seg) / (float(seg @ seg) + 1e-9)))
                c = ra + u * seg
                fit = (float(np.hypot(*c)) - r) / float(body_reach(c, face, R))
                if best is None or fit < best:
                    best = fit
        return best

    def _frozen(self, frame, now):
        pic, t, still = self.still
        if t and now - t < 1.0:
            return False
        tiny = cv2.resize(cv2.cvtColor(frame[::4, ::4], cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
        if pic is not None and float(np.abs(tiny.astype(np.int16) - pic).mean()) < 1.0:
            still += now - t
        else:
            still = 0.0
        self.still = (tiny.astype(np.int16), now, still)
        return still > LOST_STILL

    def _lost(self, why):
        self.release()
        self._end_run("lost")
        self.log(f"Not in the game anymore at {time.strftime('%H:%M')} ({why}; disconnected or kicked?). Stopped.")
        return "lost"

    def _end_run(self, how):
        if self.run_over or not self.seen:
            return
        self.run_over = True
        if self.learner is not None:
            if self.player_speed and self.H:
                self.learner.me = {"speed": self.player_speed / self.H, "delay": self.input_delay}
            run = self.learner.end_run(how)
            if run is not None:
                self.log(f"Run: {run['secs'] // 60}:{run['secs'] % 60:02d}, {run['hits']} hits "
                         f"{run['causes'] or ''}. Learned: {self.learner.summary()}")

    def _press_e(self, now):
        """In the lobby after LEAVE: don't touch the arrow keys (you'd walk away from the machine); press E."""
        lb = self.lobby
        self.release()
        if now - lb["left"] < E_AFTER_LEAVE or not self.io.focused():
            return "restarting"
        if lb["e"] == 0 or (now - lb["last_e"] > E_RETRY and lb["e"] < E_TRIES):
            self.io.tap("e")
            lb["e"] += 1
            lb["last_e"] = now
            if lb["e"] > 1:
                self.log(f"No game yet: pressed E again ({lb['e']}/{E_TRIES}).")
        return "restarting"

    def _auto_restart(self, frame, now):
        r = self.restart
        if r is None:
            r = self.restart = {"since": now, "clicks": 0, "last_click": 0.0, "secs": self.run_seconds()}
            self.log(f"Game over after {r['secs']:.0f} s. Auto restart: clicking LEAVE.")
        if now - r["since"] < 1.0 or now - r["last_click"] < 3.0:
            return "restarting"  # let the screen finish appearing / give the last click time to work
        if r["clicks"] >= 3:
            info = game_over_info(frame)
            self.log(f"Auto restart failed: clicked LEAVE 3 times but the GAME OVER screen stayed "
                     f"(background {info['border']}, middle {info['middle']}). Stopped.")
            self.restart = None
            return "dead"
        pos = find_leave(frame)
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
        if self.recording and t - self.recording[-1][0] < 1 / 10:
            return
        t1 = time.perf_counter()
        small = cv2.resize(last["frame"], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        cap = getattr(self.io, "capture", None)
        info = {"t": round(t, 3), "player": last["player"] and [round(v, 1) for v in last["player"]],
                "keys": list(last["keys"]), "aim": last["aim"] and [round(v) for v in last["aim"]],
                "things": [[th.kind, round(th.x), round(th.y), round(th.r)] for th in last["things"]],
                "speed": round(last.get("speed", 0) or 0), "delay": round(last.get("delay", 0) or 0, 3),
                "note": last.get("note", ""), "ms": dict(getattr(self, "ms", {}),
                                                          record=round(1000 * (time.perf_counter() - t1), 1)),
                "capture": getattr(cap, "method", "")}
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
