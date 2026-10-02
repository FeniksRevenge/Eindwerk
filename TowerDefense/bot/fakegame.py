"""
A fake version of the Roblox game, drawn with pieces cut from real screenshots, for testing the whole bot
(seeing, following, deciding, keys with delay) without Roblox. Not part of the app.

Rules (as described by the player):
  - you: stop instantly, HP 10, every hit -2 HP, briefly invincible after a hit; a bit faster than grunts
  - grunts walk at you (0.88x your speed); tiny tanks are as fast as you; tanks are slow and split into 3 tiny ones
  - orange shooters keep their distance and fire single shots at you (straight lines)
  - yellow mobs walk at you and fire rotating rings of bullets
  - boss wave: only the boss; 4 bullet rings, then it summons 3 grunts; slow, sometimes rushes
  - green health circles (+2 HP) drop sometimes and disappear after a few seconds
  - enemies come from the edges and appear inside; a wave banner shows between waves

Usage: python fakegame.py [seconds] [seeds] [input delay]
"""

import math
import os
import random
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TESTS = os.path.join(HERE, "tests")

W, H = 1984, 1116
V = 0.5 * H                      # your speed (px/s)
SPR = {}


def sprite(name):
    if name not in SPR:
        SPR[name] = cv2.imread(os.path.join(TESTS, "sprites", name + ".png"))
    return SPR[name]


def paste(img, spr, cx, cy):
    h, w = spr.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    a0, b0 = max(0, x0), max(0, y0)
    a1, b1 = min(W, x0 + w), min(H, y0 + h)
    if a1 <= a0 or b1 <= b0:
        return
    region = img[b0:b1, a0:a1]
    np.maximum(region, spr[b0 - y0:b1 - y0, a0 - x0:a1 - x0], out=region)


def rotated(spr, ang, center=None):
    h, w = spr.shape[:2]
    c = center or (w / 2, h / 2)
    size = int(math.hypot(w, h)) + 4
    M = cv2.getRotationMatrix2D(c, ang, 1.0)
    M[0, 2] += size / 2 - c[0]
    M[1, 2] += size / 2 - c[1]
    return cv2.warpAffine(spr, M, (size, size), borderValue=(0, 0, 0))


class Obj:
    def __init__(self, kind, x, y, r, hp=1, vx=0.0, vy=0.0, src=""):
        self.kind, self.x, self.y, self.r, self.hp, self.vx, self.vy, self.src = kind, x, y, r, hp, vx, vy, src
        self.cd, self.cd2, self.rot, self.ang, self.rush, self.waves = 1.5, 3.0, 0.0, 0.0, 0.0, 0
        self.ttl = 5.0


RADIUS = {"grunt": 30, "tiny": 24, "tank": 55, "shooter": 27, "yellow": 33, "boss": 100}
HP = {"grunt": 3, "tiny": 1, "tank": 10, "shooter": 3, "yellow": 4, "boss": 120}
BOSS_EVERY = 10      # a boss wave every this many waves (guess)
HP_GROWTH = 1.5      # after each boss wave every enemy (the boss too) has this much more HP; same damage (guess)
SPEED = {"grunt": 0.88, "tiny": 1.0, "tank": 0.45, "shooter": 0.6, "yellow": 0.55, "boss": 0.3}
BULLET_SPEED = {"orange": 0.9, "yellow": 0.65, "red": 0.55}   # x your speed

# Measured in the real game (tests/calibrate.py writes this from a learned.json): replaces the guesses.
CALIBRATION = os.path.join(TESTS, "calibration.json")
if os.path.exists(CALIBRATION):
    import json
    with open(CALIBRATION) as _f:
        _cal = json.load(_f)
    SPEED.update({k: v for k, v in _cal.get("speed", {}).items() if k in SPEED})
    BULLET_SPEED.update({k: v for k, v in _cal.get("bullet_speed", {}).items() if k in BULLET_SPEED})


class Game:
    def __init__(self, seed=0, key_delay=0.12, boss_wave=False):
        self.rnd = random.Random(seed)
        self.t = 0.0
        self.px, self.py = W / 2, H / 2
        self.hp, self.hits, self.kills, self.dead = 10, 0, 0, False
        self.hit_log = []
        self.last_hit = -9.0
        self.keys, self.queue, self.key_delay = (), [], key_delay
        self.aim, self.firing = None, False
        self.mobs, self.bullets, self.shots, self.pickups = [], [], [], []
        self.shot_cd = 0.0
        self.wave, self.banner_until, self.next_spawn = 0, 0.0, 0.0
        self.boss_wave = boss_wave
        self.stars = [(self.rnd.uniform(0, W), self.rnd.uniform(0, H), self.rnd.choice([6, 8, 10]),
                       self.rnd.choice([(23, 21, 95), (28, 27, 127), (30, 29, 140), (20, 14, 40)])) for _ in range(180)]
        self.ufo_ang = 0.0
        self.chat = self.rnd.random() < 0.5
        self.next_wave()

    # ------------------------------------------------------------------ waves
    def hp_scale(self):
        """Enemies get tougher after every boss wave you've beaten (same damage, more HP)."""
        return HP_GROWTH ** ((self.wave - 1) // BOSS_EVERY)

    def next_wave(self):
        self.wave += 1
        self.banner_until = self.t + 2.0
        if self.boss_wave:
            self.spawn("boss", W * 0.25, H * 0.3)
            return
        n = 3 + self.wave
        kinds = ["grunt"] * 4 + ["shooter"] * 2 + ["yellow"] + ["tank"]
        if self.wave >= 15:  # late waves (as recorded at wave 31): many shooters and tanks
            kinds = ["grunt"] * 3 + ["shooter"] * 5 + ["yellow"] + ["tank"] * 3
        self.pending = [self.rnd.choice(kinds) for _ in range(n)]
        self.next_spawn = self.t + 2.0

    def spawn(self, kind, x=None, y=None):
        if x is None:
            if self.rnd.random() < 0.6:  # from an edge
                side = self.rnd.randrange(4)
                x, y = ((self.rnd.uniform(0, W), -20) if side == 0 else (self.rnd.uniform(0, W), H + 20) if side == 1
                        else (-20, self.rnd.uniform(0, H)) if side == 2 else (W + 20, self.rnd.uniform(0, H)))
            else:  # appears inside, not right on top of you
                while True:
                    x, y = self.rnd.uniform(100, W - 100), self.rnd.uniform(100, H - 100)
                    if math.hypot(x - self.px, y - self.py) > 450:
                        break
        o = Obj(kind, x, y, RADIUS[kind], HP[kind] * self.hp_scale())
        o.cd = self.rnd.uniform(0.8, 2.0)
        o.ang = self.rnd.uniform(0, 90)
        self.mobs.append(o)

    # ------------------------------------------------------------------ one tick
    def step(self, dt):
        if self.dead:
            return
        self.t += dt
        while self.queue and self.queue[0][0] <= self.t:
            _, kind, val = self.queue.pop(0)
            if kind == "keys":
                self.keys = val
            else:
                self.firing = val
        dx = ("right" in self.keys) - ("left" in self.keys)
        dy = ("down" in self.keys) - ("up" in self.keys)
        n = math.hypot(dx, dy) or 1
        if self.aim is not None:  # the UFO faces the mouse
            self.ufo_ang = math.degrees(math.atan2(self.aim[1] - self.py, self.aim[0] - self.px))
        self.px = min(max(self.px + dx / n * V * dt, 20), W - 20)
        self.py = min(max(self.py + dy / n * V * dt, 20), H - 20)

        # waves
        if not self.boss_wave:
            if getattr(self, "pending", None) and self.t >= self.next_spawn:
                self.spawn(self.pending.pop())
                self.next_spawn = self.t + 0.8
            if not getattr(self, "pending", None) and not self.mobs:
                self.next_wave()

        # your gun
        self.shot_cd -= dt
        if self.firing and self.aim and self.shot_cd <= 0:
            self.shot_cd = 0.15
            d = math.hypot(self.aim[0] - self.px, self.aim[1] - self.py) or 1
            self.shots.append(Obj("shot", self.px, self.py, 6, vx=(self.aim[0] - self.px) / d * 2.4 * V,
                                  vy=(self.aim[1] - self.py) / d * 2.4 * V))

        for o in list(self.mobs):
            d = math.hypot(self.px - o.x, self.py - o.y) or 1
            nx, ny = (self.px - o.x) / d, (self.py - o.y) / d
            sp = SPEED[o.kind] * V
            o.cd -= dt
            if o.kind == "shooter":
                want = 1 if d > 0.45 * H else -1 if d < 0.3 * H else 0
                o.x = min(max(o.x + (nx * want - ny * 0.5) * sp * dt, 40), W - 40)
                o.y = min(max(o.y + (ny * want + nx * 0.5) * sp * dt, 40), H - 40)
                if o.cd <= 0:
                    o.cd = 1.4
                    self.bullets.append(Obj("bullet", o.x, o.y, 10, vx=nx * BULLET_SPEED["orange"] * V,
                                           vy=ny * BULLET_SPEED["orange"] * V, src="orange"))
            elif o.kind == "yellow":
                o.x += nx * sp * dt
                o.y += ny * sp * dt
                if o.cd <= 0:
                    o.cd, o.rot = 2.0, o.rot + 0.3
                    for i in range(8):
                        a = o.rot + i * math.pi / 4
                        self.bullets.append(Obj("bullet", o.x, o.y, 10, vx=math.cos(a) * BULLET_SPEED["yellow"] * V,
                                                    vy=math.sin(a) * BULLET_SPEED["yellow"] * V, src="yellow"))
            elif o.kind == "boss":
                o.rush -= dt
                o.cd2 -= dt
                if o.cd2 <= 0:
                    o.cd2, o.rush = 8.0, 0.8
                bsp = 1.4 * V if o.rush > 0 else sp
                o.x += nx * bsp * dt
                o.y += ny * bsp * dt
                if o.cd <= 0:
                    if o.waves < 4:
                        o.cd, o.rot, o.waves = 0.7, o.rot + 0.17, o.waves + 1
                        for i in range(18):
                            a = o.rot + i * 2 * math.pi / 18
                            self.bullets.append(Obj("bullet", o.x, o.y, 11, vx=math.cos(a) * BULLET_SPEED["red"] * V,
                                                        vy=math.sin(a) * BULLET_SPEED["red"] * V, src="red"))
                    else:
                        o.cd, o.waves = 4.0, 0
                        for i in range(3):
                            a = self.rnd.uniform(0, 2 * math.pi)
                            self.spawn("grunt", o.x + math.cos(a) * 160, o.y + math.sin(a) * 160)
            else:
                o.x += nx * sp * dt
                o.y += ny * sp * dt
            o.ang += 40 * dt

        for b in self.bullets + self.shots:
            b.x += b.vx * dt
            b.y += b.vy * dt
        inside = lambda b: -40 < b.x < W + 40 and -40 < b.y < H + 40
        self.bullets = [b for b in self.bullets if inside(b)]
        keep = []
        for s in self.shots:
            hit = next((o for o in self.mobs if math.hypot(o.x - s.x, o.y - s.y) < o.r + s.r), None)
            if hit is None:
                if inside(s):
                    keep.append(s)
                continue
            hit.hp -= 1
            if hit.hp <= 0:
                self.mobs.remove(hit)
                self.kills += 1
                if hit.kind == "tank":
                    for i in range(3):
                        a = i * 2 * math.pi / 3
                        self.spawn("tiny", hit.x + math.cos(a) * 40, hit.y + math.sin(a) * 40)
                if self.rnd.random() < 0.08:
                    self.pickups.append(Obj("health", hit.x, hit.y, 9))
                if hit.kind == "boss":
                    self.spawn("boss", W * self.rnd.uniform(0.2, 0.8), -100)
        self.shots = keep
        for p in list(self.pickups):
            p.ttl -= dt
            if p.ttl <= 0:
                self.pickups.remove(p)
            elif math.hypot(p.x - self.px, p.y - self.py) < p.r + 20:
                self.pickups.remove(p)
                self.hp = min(10, self.hp + 2)
        # hits (invincible for 1 s after a hit); hit size = the gray ball
        if self.t - self.last_hit > 1.0:
            for o in self.mobs + self.bullets:
                if self.body_gap(o) < 0:
                    self.hits += 1
                    self.hit_log.append((round(self.t, 1), o.kind + ("/" + o.src if o.src else "")))
                    self.hp -= 2
                    self.last_hit = self.t
                    if self.hp <= 0:
                        self.dead = True
                    break

    def body_gap(self, o):
        """Distance from o to your body: the ball (r 19) and the saucer behind it, as an oval
        (as measured on the real game: 0.35 R behind the ball, 1.0 R long, 1.55 R wide, R = 28)."""
        a = math.radians(self.ufo_ang)
        fx, fy = math.cos(a), math.sin(a)
        cx, cy = self.px - fx * 0.35 * 28, self.py - fy * 0.35 * 28
        vx, vy = o.x - cx, o.y - cy
        n = math.hypot(vx, vy) or 1e-9
        c = (vx * fx + vy * fy) / n
        reach = 1 / math.sqrt(c * c / 28.0 ** 2 + (1 - c * c) / (1.55 * 28) ** 2)
        return n - reach - o.r

    # ------------------------------------------------------------------ the picture
    def render(self):
        img = np.full((H, W, 3), (8, 5, 4), np.uint8)
        for x, y, s, c in self.stars:
            cv2.rectangle(img, (int(x), int(y)), (int(x) + s, int(y) + s), c, -1)
        for p in self.pickups:
            col = (90, 225, 95)
            cv2.circle(img, (int(p.x), int(p.y)), 9, col, 2)
            cv2.rectangle(img, (int(p.x) - 3, int(p.y) - 3), (int(p.x) + 3, int(p.y) + 3), col, -1)
        for o in self.mobs:
            if o.kind in ("grunt", "tank", "tiny"):
                paste(img, rotated(sprite(o.kind), o.ang), o.x, o.y)
            else:
                paste(img, sprite(o.kind), o.x, o.y)
        for b in self.bullets:
            paste(img, sprite({"orange": "orange_bullet", "yellow": "yellow_bullet"}.get(b.src, "red_bullet")), b.x, b.y)
        for s in self.shots:
            cv2.circle(img, (int(s.x), int(s.y)), 5, (235, 235, 240), -1)
        if self.aim:  # the game's aim line and crosshair
            cv2.line(img, (int(self.px), int(self.py)), (int(self.aim[0]), int(self.aim[1])), (20, 18, 70), 2)
            cv2.circle(img, (int(self.aim[0]), int(self.aim[1])), 12, (60, 60, 60), 1)
        blink = (self.t - self.last_hit) < 1.0 and int(self.t * 10) % 2 == 0
        if not blink:
            ufo = rotated(sprite("ufo"), -self.ufo_ang + 180, center=(35, 51))
            paste(img, ufo, self.px, self.py)
        # HUD
        for name, x, y in (("hud_hp", 40, 40), ("hud_score", 1495, 40), ("hud_hints", 395, 1055)):
            paste(img, sprite(name), x + sprite(name).shape[1] / 2, y + sprite(name).shape[0] / 2)
        if self.chat:
            paste(img, sprite("hud_chat"), 172, 195)
        if self.t < self.banner_until:
            paste(img, sprite("hud_banner"), 1002, 155)
        # the HP bar: the red part shrinks with your HP (the sprite is a full bar; drawn last:
        # the chat sprite was cut from a screenshot with the bar in it)
        hp_sp = sprite("hud_hp")
        fill = (np.abs(hp_sp.astype(int) - (19, 16, 39)).sum(-1) < 12)
        cols, rows = np.flatnonzero(fill.any(0)), np.flatnonzero(fill.any(1))
        x0, x1 = 40 + cols[0], 40 + cols[-1] + 1
        xe = int(x0 + (x1 - x0) * max(0, self.hp) / 10)
        part = img[40 + rows[0]:40 + rows[-1] + 1, xe:x1]
        part[fill[rows[0]:rows[-1] + 1, xe - 40:x1 - 40]] = (14, 12, 12)
        if self.t - self.last_hit < 0.15:  # the red flash when you get hit
            img = cv2.addWeighted(img, 0.4, np.full_like(img, (22, 20, 110)), 0.6, 0)
        return img


class FakeIO:
    """What the bot talks to: renders the fake game; keys/space arrive after the input delay."""

    def __init__(self, game, dt=1 / 30):
        self.g, self.dt, self.frame_time = game, dt, 0.0

    def grab(self):
        self.g.step(self.dt)
        self.frame_time = self.g.t
        return self.g.render()

    def now(self):
        return self.g.t

    def focused(self):
        return True

    def set_keys(self, keys):
        self.g.queue.append((self.g.t + self.g.key_delay, "keys", tuple(keys)))

    def fire(self, on):
        self.g.queue.append((self.g.t + self.g.key_delay, "fire", on))

    def aim(self, x, y):
        self.g.aim = (x, y)

    def tap(self, name):
        pass

    def click(self, x, y):
        pass

    def release(self):
        self.set_keys(())
        self.fire(False)


def play(seed, seconds=60, delay=0.12, boss=False, video=None, learner=None):
    from runner import BotRunner
    g = Game(seed, key_delay=delay, boss_wave=boss)
    bot = BotRunner(FakeIO(g), learner=learner)
    out = None
    while g.t < seconds and not g.dead:
        bot.step()
        if video is not None and int(g.t * 30) % 3 == 0:
            frame, pic = bot.picture()
            if pic is not None:
                if out is None:
                    out = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), 10, (W // 2, H // 2))
                out.write(cv2.resize(pic, (W // 2, H // 2)))
    if out is not None:
        out.release()
    if learner is not None:
        bot._end_run("game over" if g.dead else "stopped")
    seen = [c for k, c in bot.events if k == "hit"]
    return {"seen_hits": seen, "t": round(g.t), "hits": g.hits, "what": g.hit_log, "dead": g.dead, "kills": g.kills, "wave": g.wave,
            "speed": round(bot.player_speed or 0), "delay": round(bot.input_delay, 2)}


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 0.12
    boss = len(sys.argv) > 4 and sys.argv[4] == "boss"
    learner = None
    if os.environ.get("LEARN"):  # LEARN=file.json: learn across the games, like the app does
        from learn import Learner
        learner = Learner(os.environ["LEARN"])
    tot_hits, tot_t = 0, 0.0
    for seed in range(seeds):
        r = play(seed, secs, delay, boss, learner=learner)
        if learner is not None:
            r["room"] = {k: round(v, 2) for k, v in learner.room.items() if v > 1.005}
        tot_hits += r["hits"]
        tot_t += r["t"]
        print(r, flush=True)
    print(f"hits per minute: {tot_hits / (tot_t / 60):.2f}")
