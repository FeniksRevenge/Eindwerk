"""
Tower Defense Shooter
---------------------
Mobs walk a path toward your base. You run around and shoot them yourself,
and you can drop towers with the gold you earn.

One hit and you're dead: touching a mob or getting hit by a mob bullet ends
the run. If too many mobs reach the base, you also lose.

Controls
  WASD            move
  Mouse           aim
  Left mouse      shoot (hold)
  1 / 2           select tower (Gun / Cannon), press again to deselect
  Right mouse     place selected tower
  Space           start next wave early
  P / Esc         pause
  R               restart (after game over)
"""

import math
import random
import sys

import pygame

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 1280, 720
FPS = 60

BG_COLOR = (24, 28, 34)
GRID_COLOR = (32, 37, 45)
PATH_COLOR = (58, 52, 44)
PATH_EDGE = (78, 70, 58)
PATH_WIDTH = 56

PLAYER_RADIUS = 13
PLAYER_SPEED = 260
PLAYER_FIRE_DELAY = 0.11
BULLET_SPEED = 820
BULLET_DAMAGE = 10

BASE_MAX_HP = 20
START_GOLD = 100
WAVE_BREAK = 8.0  # seconds between waves

# Path waypoints (mobs walk these in order, last one is the base)
PATH = [
    (-40, 140),
    (260, 140),
    (260, 460),
    (560, 460),
    (560, 220),
    (880, 220),
    (880, 560),
    (1140, 560),
    (1140, 330),
]
BASE_POS = PATH[-1]
BASE_RADIUS = 38

# name: (hp, speed, radius, color, gold, shoots)
MOB_TYPES = {
    "grunt":   dict(hp=30,  speed=70,  radius=13, color=(220, 80, 80),  gold=5,  shoots=False),
    "runner":  dict(hp=18,  speed=135, radius=10, color=(240, 180, 60), gold=6,  shoots=False),
    "tank":    dict(hp=160, speed=42,  radius=20, color=(150, 90, 200), gold=18, shoots=False),
    "shooter": dict(hp=40,  speed=60,  radius=14, color=(80, 200, 220), gold=10, shoots=True),
}

# name: (cost, range, fire delay, damage, bullet speed, splash radius, color)
TOWER_TYPES = {
    "gun":    dict(cost=50,  range=170, delay=0.35, damage=8,  speed=700, splash=0,  color=(90, 170, 255), key="1"),
    "cannon": dict(cost=120, range=210, delay=1.4,  damage=40, speed=420, splash=60, color=(255, 140, 70), key="2"),
}
TOWER_RADIUS = 18


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def dist_point_segment(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dist_to_path(p):
    return min(dist_point_segment(p, PATH[i], PATH[i + 1]) for i in range(len(PATH) - 1))


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Player:
    def __init__(self):
        self.pos = pygame.Vector2(WIDTH / 2, HEIGHT / 2 + 180)
        self.cooldown = 0.0
        self.aim = pygame.Vector2(1, 0)

    def update(self, dt, keys, mouse_pos):
        move = pygame.Vector2(
            (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT]),
            (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        if move.length_squared() > 0:
            move = move.normalize()
        self.pos += move * PLAYER_SPEED * dt
        self.pos.x = max(PLAYER_RADIUS, min(WIDTH - PLAYER_RADIUS, self.pos.x))
        self.pos.y = max(PLAYER_RADIUS, min(HEIGHT - PLAYER_RADIUS, self.pos.y))

        to_mouse = pygame.Vector2(mouse_pos) - self.pos
        if to_mouse.length_squared() > 1:
            self.aim = to_mouse.normalize()
        self.cooldown = max(0.0, self.cooldown - dt)

    def try_shoot(self):
        if self.cooldown > 0:
            return None
        self.cooldown = PLAYER_FIRE_DELAY
        spread = random.uniform(-0.04, 0.04)
        direction = self.aim.rotate_rad(spread)
        start = self.pos + self.aim * (PLAYER_RADIUS + 6)
        return Bullet(start, direction * BULLET_SPEED, BULLET_DAMAGE, (255, 245, 170), friendly=True)

    def draw(self, surf):
        tip = self.pos + self.aim * (PLAYER_RADIUS + 10)
        pygame.draw.line(surf, (200, 200, 210), self.pos, tip, 6)
        pygame.draw.circle(surf, (120, 230, 140), self.pos, PLAYER_RADIUS)
        pygame.draw.circle(surf, (230, 255, 235), self.pos, PLAYER_RADIUS, 2)


class Bullet:
    def __init__(self, pos, vel, damage, color, friendly, splash=0, radius=4):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.damage = damage
        self.color = color
        self.friendly = friendly
        self.splash = splash
        self.radius = radius
        self.alive = True

    def update(self, dt):
        self.pos += self.vel * dt
        if not (-20 < self.pos.x < WIDTH + 20 and -20 < self.pos.y < HEIGHT + 20):
            self.alive = False

    def draw(self, surf):
        pygame.draw.circle(surf, self.color, self.pos, self.radius)


class Mob:
    def __init__(self, kind, hp_mult):
        spec = MOB_TYPES[kind]
        self.kind = kind
        self.max_hp = spec["hp"] * hp_mult
        self.hp = self.max_hp
        self.speed = spec["speed"]
        self.radius = spec["radius"]
        self.color = spec["color"]
        self.gold = spec["gold"]
        self.shoots = spec["shoots"]
        self.pos = pygame.Vector2(PATH[0])
        self.target_idx = 1
        self.alive = True
        self.reached_base = False
        self.shoot_timer = random.uniform(1.0, 2.5)
        self.hit_flash = 0.0
        self.progress = 0.0  # distance travelled, used by towers to pick the lead mob

    def update(self, dt, player, bullets):
        remaining = self.speed * dt
        while remaining > 0 and self.target_idx < len(PATH):
            target = pygame.Vector2(PATH[self.target_idx])
            to_target = target - self.pos
            d = to_target.length()
            if d <= remaining:
                self.pos = target
                remaining -= d
                self.progress += d
                self.target_idx += 1
            else:
                self.pos += to_target / d * remaining
                self.progress += remaining
                remaining = 0
        if self.target_idx >= len(PATH):
            self.reached_base = True
            self.alive = False

        if self.shoots:
            self.shoot_timer -= dt
            if self.shoot_timer <= 0:
                self.shoot_timer = random.uniform(1.6, 2.6)
                to_player = player.pos - self.pos
                if 0 < to_player.length() < 450:
                    direction = to_player.normalize()
                    bullets.append(Bullet(self.pos + direction * self.radius, direction * 260, 1,
                                          (255, 90, 120), friendly=False, radius=6))
        self.hit_flash = max(0.0, self.hit_flash - dt)

    def damage(self, amount):
        self.hp -= amount
        self.hit_flash = 0.08
        if self.hp <= 0:
            self.alive = False

    def draw(self, surf):
        color = (255, 255, 255) if self.hit_flash > 0 else self.color
        pygame.draw.circle(surf, color, self.pos, self.radius)
        pygame.draw.circle(surf, (20, 20, 20), self.pos, self.radius, 2)
        if self.hp < self.max_hp:
            w = self.radius * 2
            x = self.pos.x - self.radius
            y = self.pos.y - self.radius - 8
            pygame.draw.rect(surf, (60, 20, 20), (x, y, w, 4))
            pygame.draw.rect(surf, (90, 220, 90), (x, y, w * max(0, self.hp) / self.max_hp, 4))


class Tower:
    def __init__(self, kind, pos):
        self.kind = kind
        self.spec = TOWER_TYPES[kind]
        self.pos = pygame.Vector2(pos)
        self.cooldown = 0.0
        self.angle = 0.0

    def update(self, dt, mobs, bullets):
        self.cooldown = max(0.0, self.cooldown - dt)
        in_range = [m for m in mobs if m.pos.distance_to(self.pos) <= self.spec["range"]]
        if not in_range:
            return
        target = max(in_range, key=lambda m: m.progress)
        direction = target.pos - self.pos
        if direction.length_squared() == 0:
            return
        direction = direction.normalize()
        self.angle = math.atan2(direction.y, direction.x)
        if self.cooldown == 0:
            self.cooldown = self.spec["delay"]
            bullets.append(Bullet(self.pos + direction * TOWER_RADIUS, direction * self.spec["speed"],
                                  self.spec["damage"], self.spec["color"], friendly=True,
                                  splash=self.spec["splash"], radius=7 if self.spec["splash"] else 4))

    def draw(self, surf, show_range=False):
        if show_range:
            draw_range(surf, self.pos, self.spec["range"], (255, 255, 255, 25))
        pygame.draw.rect(surf, (70, 75, 85), (self.pos.x - TOWER_RADIUS, self.pos.y - TOWER_RADIUS,
                                              TOWER_RADIUS * 2, TOWER_RADIUS * 2), border_radius=5)
        barrel = self.pos + pygame.Vector2(math.cos(self.angle), math.sin(self.angle)) * (TOWER_RADIUS + 6)
        pygame.draw.line(surf, (200, 200, 210), self.pos, barrel, 8 if self.kind == "cannon" else 5)
        pygame.draw.circle(surf, self.spec["color"], self.pos, TOWER_RADIUS - 6)


class Particle:
    def __init__(self, pos, color):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1)) * random.uniform(60, 220)
        self.life = random.uniform(0.25, 0.55)
        self.color = color

    def update(self, dt):
        self.pos += self.vel * dt
        self.vel *= 0.9
        self.life -= dt

    def draw(self, surf):
        if self.life > 0:
            pygame.draw.circle(surf, self.color, self.pos, max(1, int(self.life * 8)))


def draw_range(surf, pos, radius, rgba):
    overlay = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(overlay, rgba, (radius, radius), radius)
    pygame.draw.circle(overlay, (rgba[0], rgba[1], rgba[2], 90), (radius, radius), radius, 2)
    surf.blit(overlay, (pos[0] - radius, pos[1] - radius))


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont("consolas,menlo,monospace", 20)
        self.big_font = pygame.font.SysFont("consolas,menlo,monospace", 56, bold=True)
        self.background = self.build_background()
        self.reset()

    def build_background(self):
        bg = pygame.Surface((WIDTH, HEIGHT))
        bg.fill(BG_COLOR)
        for x in range(0, WIDTH, 40):
            pygame.draw.line(bg, GRID_COLOR, (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, 40):
            pygame.draw.line(bg, GRID_COLOR, (0, y), (WIDTH, y))
        for i in range(len(PATH) - 1):
            pygame.draw.line(bg, PATH_EDGE, PATH[i], PATH[i + 1], PATH_WIDTH + 6)
        for p in PATH:
            pygame.draw.circle(bg, PATH_EDGE, p, (PATH_WIDTH + 6) // 2)
        for i in range(len(PATH) - 1):
            pygame.draw.line(bg, PATH_COLOR, PATH[i], PATH[i + 1], PATH_WIDTH)
        for p in PATH:
            pygame.draw.circle(bg, PATH_COLOR, p, PATH_WIDTH // 2)
        return bg

    def reset(self):
        self.player = Player()
        self.mobs = []
        self.bullets = []
        self.towers = []
        self.particles = []
        self.gold = START_GOLD
        self.base_hp = BASE_MAX_HP
        self.wave = 0
        self.spawn_queue = []
        self.spawn_timer = 0.0
        self.break_timer = 4.0
        self.kills = 0
        self.selected_tower = None
        self.game_over = False
        self.death_reason = ""
        self.paused = False
        self.message = ""
        self.message_timer = 0.0

    # -- waves --------------------------------------------------------------
    def start_next_wave(self):
        self.wave += 1
        w = self.wave
        queue = ["grunt"] * (6 + w * 2)
        if w >= 2:
            queue += ["runner"] * (w * 2)
        if w >= 3:
            queue += ["shooter"] * (w - 1)
        if w >= 4:
            queue += ["tank"] * (w // 2)
        random.shuffle(queue)
        self.spawn_queue = queue
        self.spawn_interval = max(0.25, 0.9 - w * 0.05)
        self.spawn_timer = 0.0
        self.hp_mult = 1.0 + (w - 1) * 0.15
        self.flash(f"Wave {w}")

    def wave_active(self):
        return bool(self.spawn_queue) or bool(self.mobs)

    def flash(self, text):
        self.message = text
        self.message_timer = 1.8

    # -- input --------------------------------------------------------------
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_p, pygame.K_ESCAPE) and not self.game_over:
                self.paused = not self.paused
            elif event.key == pygame.K_r and self.game_over:
                self.reset()
            elif event.key == pygame.K_SPACE and not self.game_over and not self.wave_active():
                self.break_timer = 0.0
            elif event.key in (pygame.K_1, pygame.K_2):
                kind = "gun" if event.key == pygame.K_1 else "cannon"
                self.selected_tower = None if self.selected_tower == kind else kind
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self.try_place_tower(event.pos)

    def can_place(self, pos):
        if self.selected_tower is None:
            return False
        if dist_to_path(pos) < PATH_WIDTH / 2 + TOWER_RADIUS:
            return False
        if pygame.Vector2(pos).distance_to(BASE_POS) < BASE_RADIUS + TOWER_RADIUS + 10:
            return False
        if not (TOWER_RADIUS < pos[0] < WIDTH - TOWER_RADIUS and 60 < pos[1] < HEIGHT - TOWER_RADIUS):
            return False
        return all(t.pos.distance_to(pos) >= TOWER_RADIUS * 2 + 4 for t in self.towers)

    def try_place_tower(self, pos):
        if self.game_over or self.paused or self.selected_tower is None:
            return
        cost = TOWER_TYPES[self.selected_tower]["cost"]
        if self.gold < cost:
            self.flash("Not enough gold")
            return
        if not self.can_place(pos):
            self.flash("Can't build there")
            return
        self.gold -= cost
        self.towers.append(Tower(self.selected_tower, pos))

    # -- update -------------------------------------------------------------
    def update(self, dt):
        self.message_timer = max(0.0, self.message_timer - dt)
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        if self.game_over or self.paused:
            return

        keys = pygame.key.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        self.player.update(dt, keys, mouse_pos)
        if pygame.mouse.get_pressed()[0]:
            b = self.player.try_shoot()
            if b:
                self.bullets.append(b)

        # waves
        if not self.wave_active():
            self.break_timer -= dt
            if self.break_timer <= 0:
                self.start_next_wave()
                self.break_timer = WAVE_BREAK
        if self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                self.mobs.append(Mob(self.spawn_queue.pop(), self.hp_mult))
                self.spawn_timer = self.spawn_interval

        for m in self.mobs:
            m.update(dt, self.player, self.bullets)
        for t in self.towers:
            t.update(dt, self.mobs, self.bullets)
        for b in self.bullets:
            b.update(dt)

        self.resolve_collisions()

        for m in self.mobs:
            if m.reached_base:
                self.base_hp -= 2 if m.kind == "tank" else 1
                self.burst(m.pos, (255, 80, 80), 14)
        self.mobs = [m for m in self.mobs if m.alive]
        self.bullets = [b for b in self.bullets if b.alive]

        if self.base_hp <= 0:
            self.base_hp = 0
            self.end("The base was overrun")

    def resolve_collisions(self):
        ppos = self.player.pos
        for b in self.bullets:
            if not b.alive:
                continue
            if b.friendly:
                for m in self.mobs:
                    if m.alive and b.pos.distance_to(m.pos) <= m.radius + b.radius:
                        b.alive = False
                        if b.splash:
                            self.burst(b.pos, (255, 160, 80), 12)
                            for other in self.mobs:
                                if other.alive and other.pos.distance_to(b.pos) <= b.splash + other.radius:
                                    self.hit_mob(other, b.damage)
                        else:
                            self.hit_mob(m, b.damage)
                        break
            elif b.pos.distance_to(ppos) <= PLAYER_RADIUS + b.radius:
                self.end("You got shot")
                return

        for m in self.mobs:
            if m.alive and m.pos.distance_to(ppos) <= m.radius + PLAYER_RADIUS:
                self.end(f"A {m.kind} got you")
                return

    def hit_mob(self, mob, damage):
        mob.damage(damage)
        if not mob.alive:
            self.gold += mob.gold
            self.kills += 1
            self.burst(mob.pos, mob.color, 10)

    def burst(self, pos, color, n):
        self.particles.extend(Particle(pos, color) for _ in range(n))

    def end(self, reason):
        if not self.game_over:
            self.game_over = True
            self.death_reason = reason
            self.burst(self.player.pos, (120, 230, 140), 30)

    # -- draw ---------------------------------------------------------------
    def draw(self):
        s = self.screen
        s.blit(self.background, (0, 0))
        mouse = pygame.mouse.get_pos()

        # base
        pygame.draw.circle(s, (60, 110, 200), BASE_POS, BASE_RADIUS)
        pygame.draw.circle(s, (170, 210, 255), BASE_POS, BASE_RADIUS, 3)
        label = self.font.render("BASE", True, (230, 240, 255))
        s.blit(label, label.get_rect(center=BASE_POS))

        for t in self.towers:
            t.draw(s, show_range=t.pos.distance_to(mouse) < TOWER_RADIUS)
        for m in self.mobs:
            m.draw(s)
        for b in self.bullets:
            b.draw(s)
        if not self.game_over:
            self.player.draw(s)
        for p in self.particles:
            p.draw(s)

        # tower placement ghost
        if self.selected_tower and not self.game_over:
            spec = TOWER_TYPES[self.selected_tower]
            ok = self.can_place(mouse) and self.gold >= spec["cost"]
            draw_range(s, mouse, spec["range"], (80, 255, 120, 30) if ok else (255, 80, 80, 30))
            ghost = pygame.Surface((TOWER_RADIUS * 2, TOWER_RADIUS * 2), pygame.SRCALPHA)
            ghost.fill((*spec["color"], 120))
            s.blit(ghost, (mouse[0] - TOWER_RADIUS, mouse[1] - TOWER_RADIUS))
        else:
            pygame.draw.circle(s, (255, 255, 255), mouse, 8, 1)
            pygame.draw.line(s, (255, 255, 255), (mouse[0] - 12, mouse[1]), (mouse[0] + 12, mouse[1]))
            pygame.draw.line(s, (255, 255, 255), (mouse[0], mouse[1] - 12), (mouse[0], mouse[1] + 12))

        self.draw_hud()

    def draw_hud(self):
        s = self.screen
        bar = pygame.Surface((WIDTH, 44), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 150))
        s.blit(bar, (0, 0))

        if self.wave_active():
            status = f"{len(self.mobs) + len(self.spawn_queue)} mobs left"
        else:
            status = f"next wave in {max(0, self.break_timer):.0f}s  [Space]"
        parts = [
            (f"Wave {self.wave}", (230, 230, 230)),
            (f"Base {self.base_hp}/{BASE_MAX_HP}", (255, 120, 120) if self.base_hp <= 5 else (140, 190, 255)),
            (f"Gold {self.gold}", (255, 215, 90)),
            (f"Kills {self.kills}", (200, 200, 200)),
            (status, (170, 170, 170)),
        ]
        x = 14
        for text, color in parts:
            img = self.font.render(text, True, color)
            s.blit(img, (x, 11))
            x += img.get_width() + 28

        # tower shop
        x = WIDTH - 14
        for kind in reversed(list(TOWER_TYPES)):
            spec = TOWER_TYPES[kind]
            selected = self.selected_tower == kind
            affordable = self.gold >= spec["cost"]
            color = spec["color"] if affordable else (110, 110, 110)
            img = self.font.render(f"[{spec['key']}] {kind.title()} {spec['cost']}g", True, color)
            x -= img.get_width()
            if selected:
                pygame.draw.rect(s, color, (x - 6, 6, img.get_width() + 12, 32), 2, border_radius=4)
            s.blit(img, (x, 11))
            x -= 24

        if self.message_timer > 0 and not self.game_over:
            img = self.big_font.render(self.message, True, (255, 255, 255))
            img.set_alpha(int(255 * min(1.0, self.message_timer)))
            s.blit(img, img.get_rect(center=(WIDTH / 2, 110)))

        if self.paused:
            self.center_overlay("PAUSED", "Press P or Esc to resume")
        elif self.game_over:
            self.center_overlay("GAME OVER",
                                f"{self.death_reason}  -  wave {self.wave}, {self.kills} kills.  Press R to restart")

    def center_overlay(self, title, subtitle):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        self.screen.blit(shade, (0, 0))
        t = self.big_font.render(title, True, (255, 255, 255))
        self.screen.blit(t, t.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 30)))
        st = self.font.render(subtitle, True, (210, 210, 210))
        self.screen.blit(st, st.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 25)))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Tower Defense Shooter")
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()
    game = Game(screen)

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)  # clamp so a lag spike can't teleport things
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            game.handle_event(event)
        game.update(dt)
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()
