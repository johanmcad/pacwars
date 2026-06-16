"""PAC-WARS — a Star Wars themed Pac-Man.

Fly your X-wing through the Death Star corridors, collect energy cells,
grab a Death Star core to power your lasers and hunt down the TIE fighters.

Controls: Arrow keys / WASD to move, Enter to start, Esc to quit, P to pause.
"""

import array
import math
import random
import sys

import pygame

# ---------------------------------------------------------------- constants

TILE = 32
HUD_H = 72

MAZE = [
    "###################",
    "#........#........#",
    "#o##.###.#.###.##o#",
    "#.................#",
    "#.##.#.#####.#.##.#",
    "#....#...#...#....#",
    "####.###.#.###.####",
    "####.#.......#.####",
    "####.#.##-##.#.####",
    "    .  #GGG#  .    ",
    "####.#.#####.#.####",
    "####.#.......#.####",
    "####.#.#####.#.####",
    "#........#........#",
    "#.##.###.#.###.##.#",
    "#o.#.....P.....#.o#",
    "##.#.#.#####.#.#.##",
    "#....#...#...#....#",
    "#.######.#.######.#",
    "#.................#",
    "###################",
]

ROWS = len(MAZE)
COLS = len(MAZE[0])
assert all(len(r) == COLS for r in MAZE), "maze rows must all be the same width"

WIDTH = COLS * TILE
HEIGHT = ROWS * TILE + HUD_H

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)
DIRS = [UP, DOWN, LEFT, RIGHT]

YELLOW = (255, 232, 31)        # Star Wars logo yellow
SPACE = (8, 8, 24)
WALL_FILL = (16, 24, 56)
WALL_EDGE = (64, 140, 255)
WHITE = (240, 240, 240)
GREY = (150, 150, 160)

GHOSTS = [
    # name        body colour      scatter corner (col,row)
    ("VADER",     (210, 40, 40),   (COLS - 2, 1)),
    ("BOBA",      (60, 180, 90),   (1, 1)),
    ("MAUL",      (200, 70, 200),  (COLS - 2, ROWS - 2)),
    ("TROOPER",   (210, 210, 220), (1, ROWS - 2)),
]

FRIGHT_COLOR = (40, 60, 200)
FRIGHT_FLASH = (220, 220, 255)

PLAYER_SPEED = 4.4       # tiles / second
JUMP_DUR = 0.55          # seconds for a full hop
JUMP_HEIGHT = 20         # peak lift in pixels
GHOST_SPEED = 3.9
FRIGHT_SPEED = 2.6
EYES_SPEED = 7.0
FRIGHT_TIME = 7.0
SCATTER_CHASE = [(7, 20), (7, 20), (5, 20), (5, 9999)]  # (scatter, chase) seconds

# ---------------------------------------------------------------- sound

def make_tone(freq, dur, vol=0.5, shape="square"):
    rate = 22050
    n = int(rate * dur)
    buf = array.array("h")
    for i in range(n):
        t = i / rate
        if shape == "square":
            v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        else:
            v = math.sin(2 * math.pi * freq * t)
        env = min(1.0, (n - i) / (rate * 0.04))        # release
        env *= min(1.0, i / (rate * 0.004))           # attack
        buf.append(int(v * env * vol * 32000))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def make_sweep(f0, f1, dur, vol=0.5):
    rate = 22050
    n = int(rate * dur)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        f = f0 + (f1 - f0) * i / n
        phase += 2 * math.pi * f / rate
        v = 1.0 if math.sin(phase) >= 0 else -1.0
        env = min(1.0, (n - i) / (rate * 0.05))
        buf.append(int(v * env * vol * 32000))
    return pygame.mixer.Sound(buffer=buf.tobytes())


class SoundBank:
    def __init__(self):
        self.ok = True
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1)
        except pygame.error:
            self.ok = False
            return
        self.chomp = make_tone(440, 0.05, 0.25)
        self.chomp2 = make_tone(330, 0.05, 0.25)
        self.power = make_sweep(200, 900, 0.35, 0.4)
        self.eat_ghost = make_sweep(900, 200, 0.3, 0.4)
        self.death = make_sweep(700, 60, 0.9, 0.5)
        self.win = make_sweep(300, 1200, 0.6, 0.4)
        self.jump = make_sweep(320, 880, 0.18, 0.3)
        # Imperial March opening: G G G Eb Bb G Eb Bb G
        g, eb, bb = 392.0, 311.13, 466.16
        self.march = [
            (make_tone(g, 0.30, 0.5), 0.38), (make_tone(g, 0.30, 0.5), 0.38),
            (make_tone(g, 0.30, 0.5), 0.38), (make_tone(eb, 0.22, 0.5), 0.28),
            (make_tone(bb, 0.10, 0.5), 0.12), (make_tone(g, 0.30, 0.5), 0.38),
            (make_tone(eb, 0.22, 0.5), 0.28), (make_tone(bb, 0.10, 0.5), 0.12),
            (make_tone(g, 0.55, 0.5), 0.7),
        ]

    def play(self, name):
        if self.ok:
            getattr(self, name).play()


# ---------------------------------------------------------------- helpers

def tile_at(col, row):
    if 0 <= row < ROWS:
        col %= COLS
        return MAZE[row][col]
    return "#"


def walkable(col, row, is_ghost=False):
    t = tile_at(col, row)
    if t == "#":
        return False
    if t == "-" and not is_ghost:
        return False
    return True


def tile_center(col, row):
    return (col * TILE + TILE // 2, row * TILE + TILE // 2 + HUD_H)


# ---------------------------------------------------------------- actors

class Actor:
    def __init__(self, col, row, speed):
        self.col, self.row = col, row          # current tile
        self.x, self.y = float(col), float(row)  # position in tile units
        self.dir = LEFT
        self.speed = speed
        self.moving = False

    def pixel_pos(self):
        return (int(self.x * TILE + TILE // 2),
                int(self.y * TILE + TILE // 2 + HUD_H))

    def at_center(self):
        return abs(self.x - round(self.x)) < 0.08 and abs(self.y - round(self.y)) < 0.08

    def step(self, dt, is_ghost=False):
        """Move along current direction, stopping at walls, wrapping tunnels."""
        ox, oy = self.x, self.y
        dx, dy = self.dir
        nx = self.x + dx * self.speed * dt
        ny = self.y + dy * self.speed * dt
        # the tile we are moving into
        tc, tr = int(round(self.x)) + dx, int(round(self.y)) + dy
        if not walkable(tc, tr, is_ghost):
            # clamp to tile center
            if dx and (nx - round(self.x)) * dx > 0:
                nx = round(self.x)
            if dy and (ny - round(self.y)) * dy > 0:
                ny = round(self.y)
        self.x, self.y = nx, ny
        # tunnel wrap
        if self.x < -0.5:
            self.x += COLS
        elif self.x > COLS - 0.5:
            self.x -= COLS
        self.col, self.row = int(round(self.x)) % COLS, int(round(self.y))
        # treat tunnel-wrap jumps as "still moving" rather than a teleport spike
        moved = abs(self.x - ox) + abs(self.y - oy)
        self.moving = 1e-4 < moved < 1.0


class Player(Actor):
    def __init__(self, col, row):
        super().__init__(col, row, PLAYER_SPEED)
        self.want = LEFT
        self.alive = True
        self.jump_timer = 0.0

    def jump(self):
        """Start a hop if grounded. Returns True if the jump began."""
        if self.alive and self.jump_timer <= 0:
            self.jump_timer = JUMP_DUR
            return True
        return False

    @property
    def jump_height(self):
        """Normalised hop arc, 0 on the ground up to 1 at the apex."""
        if self.jump_timer <= 0:
            return 0.0
        return math.sin(math.pi * (1 - self.jump_timer / JUMP_DUR))

    @property
    def airborne(self):
        # high enough to clear a TIE fighter
        return self.jump_height > 0.4

    def update(self, dt):
        if self.jump_timer > 0:
            self.jump_timer -= dt
        if self.at_center():
            c, r = int(round(self.x)), int(round(self.y))
            if walkable(c + self.want[0], r + self.want[1]):
                if self.want != self.dir:
                    self.x, self.y = float(c), float(r)
                self.dir = self.want
        elif self.want == (-self.dir[0], -self.dir[1]):
            self.dir = self.want  # reversing is always allowed
        self.step(dt)


class Ghost(Actor):
    def __init__(self, idx, col, row):
        super().__init__(col, row, GHOST_SPEED)
        self.idx = idx
        self.name, self.color, self.corner = GHOSTS[idx]
        self.home = (col, row)
        self.state = "home"      # home, leaving, normal, frightened, eyes
        self.home_timer = idx * 3.0
        self.dir = UP

    def target(self, game):
        p = game.player
        if self.state == "eyes":
            return game.door_tile
        if game.mode == "scatter":
            return self.corner
        pc, pr = int(round(p.x)), int(round(p.y))
        if self.idx == 0:                       # Vader: direct pursuit
            return (pc, pr)
        if self.idx == 1:                       # Boba: ambush 4 ahead
            return (pc + p.dir[0] * 4, pr + p.dir[1] * 4)
        if self.idx == 2:                       # Maul: mirror through Vader
            v = game.ghosts[0]
            ax, ay = pc + p.dir[0] * 2, pr + p.dir[1] * 2
            return (2 * ax - int(round(v.x)), 2 * ay - int(round(v.y)))
        # Trooper: chase when far, retreat when close
        if (pc - self.col) ** 2 + (pr - self.row) ** 2 > 64:
            return (pc, pr)
        return self.corner

    def choose_dir(self, game):
        c, r = int(round(self.x)), int(round(self.y))
        options = []
        for d in DIRS:
            if d == (-self.dir[0], -self.dir[1]):
                continue
            nc, nr = c + d[0], r + d[1]
            ghost_pass = self.state in ("eyes", "leaving") or (self.state == "home")
            if tile_at(nc, nr) == "-" and not ghost_pass:
                continue
            if walkable(nc, nr, is_ghost=True):
                options.append(d)
        if not options:
            options = [(-self.dir[0], -self.dir[1])]
        if self.state == "frightened":
            return random.choice(options)
        tx, ty = self.target(game)
        return min(options, key=lambda d: (c + d[0] - tx) ** 2 + (r + d[1] - ty) ** 2)

    def update(self, dt, game):
        if self.state == "home":
            self.home_timer -= dt
            # bob up and down inside the pen
            self.y = self.home[1] + math.sin(pygame.time.get_ticks() * 0.005 + self.idx) * 0.2
            if self.home_timer <= 0:
                self.state = "leaving"
                self.x, self.y = float(self.home[0]), float(self.home[1])
            return
        if self.state == "leaving":
            # rise straight up through the door, then start hunting
            dc, dr = game.door_tile
            if abs(self.x - dc) > 0.05:
                self.dir = RIGHT if dc > self.x else LEFT
            else:
                self.x = float(dc)
                self.dir = UP
                if self.y <= dr - 1:
                    self.y = float(dr - 1)
                    self.row = dr - 1
                    self.state = "frightened" if game.fright_timer > 0 else "normal"
                    self.dir = random.choice([LEFT, RIGHT])
                    return
            self.x += self.dir[0] * self.speed * dt
            self.y += self.dir[1] * self.speed * dt
            return
        if self.state == "eyes":
            dc, dr = game.door_tile
            if int(round(self.x)) == dc and int(round(self.y)) == dr - 1 and self.at_center():
                # drop into the pen and respawn
                self.state = "home"
                self.home_timer = 2.0
                self.x, self.y = float(self.home[0]), float(self.home[1])
                self.speed = GHOST_SPEED
                return
        if self.at_center():
            nd = self.choose_dir(game)
            if nd != self.dir:
                self.x, self.y = float(round(self.x)), float(round(self.y))
            self.dir = nd
        self.step(dt, is_ghost=True)

    def set_frightened(self):
        if self.state == "normal":
            self.state = "frightened"
            self.speed = FRIGHT_SPEED
            self.dir = (-self.dir[0], -self.dir[1])

    def set_eaten(self):
        self.state = "eyes"
        self.speed = EYES_SPEED


# ---------------------------------------------------------------- drawing

def draw_starfield(surf, stars, t):
    for (x, y, size, phase) in stars:
        b = 90 + int(80 * (0.5 + 0.5 * math.sin(t * 2 + phase)))
        surf.fill((b, b, min(255, b + 30)), (x, y, size, size))


def draw_maze(surf):
    for r in range(ROWS):
        for c in range(COLS):
            if MAZE[r][c] == "#":
                x, y = c * TILE, r * TILE + HUD_H
                pygame.draw.rect(surf, WALL_FILL, (x + 2, y + 2, TILE - 4, TILE - 4), border_radius=6)
                pygame.draw.rect(surf, WALL_EDGE, (x + 2, y + 2, TILE - 4, TILE - 4), 2, border_radius=6)
            elif MAZE[r][c] == "-":
                x, y = c * TILE, r * TILE + HUD_H
                pygame.draw.line(surf, (180, 60, 60), (x + 4, y + TILE // 2), (x + TILE - 4, y + TILE // 2), 3)


def draw_pellet(surf, col, row, t):
    x, y = tile_center(col, row)
    # tiny four-point star (energy cell)
    s = 3 + int(1.5 * (0.5 + 0.5 * math.sin(t * 4 + col + row)))
    pygame.draw.polygon(surf, YELLOW, [(x, y - s), (x + 2, y), (x, y + s), (x - 2, y)])
    pygame.draw.polygon(surf, WHITE, [(x - s, y), (x, y - 2), (x + s, y), (x, y + 2)])


def draw_power(surf, col, row, t):
    """Power pellet drawn as a little Death Star."""
    x, y = tile_center(col, row)
    rr = 9 + int(2 * math.sin(t * 5))
    pygame.draw.circle(surf, GREY, (x, y), rr)
    pygame.draw.circle(surf, (90, 90, 100), (x, y), rr, 2)
    pygame.draw.circle(surf, (90, 90, 100), (x - rr // 3, y - rr // 3), rr // 3)
    pygame.draw.line(surf, (90, 90, 100), (x - rr, y + 2), (x + rr, y + 2), 2)


def rotate_pts(pts, ang, cx, cy):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + px * ca - py * sa, cy + px * sa + py * ca) for px, py in pts]


def draw_player(surf, player, t, fright):
    x, y = player.pixel_pos()
    ang = math.atan2(player.dir[1], player.dir[0])

    # vertical hop: a smooth arc that lifts and enlarges the ship above its shadow
    h = getattr(player, "jump_height", 0.0)
    lift = JUMP_HEIGHT * h
    scale = 1.0 + 0.45 * h
    cx, cy = x, y - lift

    # ground shadow, shrinking and fading as the ship climbs
    if h > 0.01:
        rad = max(2, int(11 * (1 - 0.45 * h)))
        sh = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, int(130 * (1 - h))),
                            (TILE // 2 - rad, TILE // 2 - rad // 2, rad * 2, rad))
        surf.blit(sh, (x - TILE // 2, y - TILE // 2))

    # S-foils flap open and shut while flying, lock half-open at rest
    moving = getattr(player, "moving", False)
    flap = 0.5 + 0.5 * math.sin(t * 18) if moving else 0.5
    spread = 5 + 8 * flap

    # X-wing: fuselage + 4 wings + engines, nose pointing along +x before rotation
    fus = [(14, 0), (4, -3), (-10, -3), (-10, 3), (4, 3)]
    wing_t = [(-2, -3), (-12, -3 - spread), (-9, -3 - spread), (1, -3)]
    wing_b = [(-2, 3), (-12, 3 + spread), (-9, 3 + spread), (1, 3)]

    def place(pts):
        return rotate_pts([(px * scale, py * scale) for px, py in pts], ang, cx, cy)

    body_col = (235, 235, 235)
    pygame.draw.polygon(surf, (200, 60, 40), place(wing_t))
    pygame.draw.polygon(surf, (200, 60, 40), place(wing_b))
    pygame.draw.polygon(surf, body_col, place(fus))
    pygame.draw.circle(surf, (255, 140, 40), place([(-11, 0)])[0], max(2, int(3 * scale)))  # engine glow
    if fright > 0:
        # lightsaber glow while powered up
        blink = fright < 2 and int(t * 8) % 2 == 0
        col = (120, 255, 120) if not blink else WHITE
        tip = place([(26, 0)])[0]
        base = place([(14, 0)])[0]
        pygame.draw.line(surf, col, base, tip, 5)
        pygame.draw.line(surf, WHITE, base, tip, 2)


def draw_ghost(surf, ghost, t, fright):
    x, y = ghost.pixel_pos()
    if ghost.state == "eyes":
        pygame.draw.circle(surf, WHITE, (x - 5, y), 4)
        pygame.draw.circle(surf, WHITE, (x + 5, y), 4)
        pygame.draw.circle(surf, (40, 40, 200), (x - 5, y), 2)
        pygame.draw.circle(surf, (40, 40, 200), (x + 5, y), 2)
        return
    if ghost.state == "frightened":
        col = FRIGHT_COLOR if not (fright < 2 and int(t * 8) % 2 == 0) else FRIGHT_FLASH
    else:
        col = ghost.color
    # TIE fighter: two hex panels + cockpit ball
    for side in (-1, 1):
        px = x + side * 11
        pts = [(px - 3, y - 13), (px + 3, y - 13), (px + 5, y), (px + 3, y + 13),
               (px - 3, y + 13), (px - 5, y)]
        pygame.draw.polygon(surf, (50, 55, 70), pts)
        pygame.draw.polygon(surf, col, pts, 2)
        pygame.draw.line(surf, col, (x, y), (px, y), 3)
    pygame.draw.circle(surf, (50, 55, 70), (x, y), 9)
    pygame.draw.circle(surf, col, (x, y), 9, 2)
    pygame.draw.circle(surf, col, (x, y), 4)


# ---------------------------------------------------------------- game

class Game:
    def __init__(self, screen, sounds, font, big_font):
        self.screen = screen
        self.sounds = sounds
        self.font = font
        self.big_font = big_font
        self.stars = [(random.randrange(WIDTH), random.randrange(HEIGHT),
                       random.choice((1, 1, 2)), random.uniform(0, 6.28))
                      for _ in range(110)]
        self.score = 0
        self.high = 0
        self.lives = 3
        self.level = 1
        self.state = "title"      # title, ready, play, dying, levelup, gameover, paused
        self.state_timer = 0
        self.chomp_alt = False
        self.reset_level(full=True)

    # -------------------------------------------------- setup

    def reset_level(self, full):
        if full:
            self.pellets = set()
            self.powers = set()
            for r in range(ROWS):
                for c in range(COLS):
                    if MAZE[r][c] == ".":
                        self.pellets.add((c, r))
                    elif MAZE[r][c] == "o":
                        self.powers.add((c, r))
        self.door_tile = next((c, r) for r in range(ROWS) for c in range(COLS) if MAZE[r][c] == "-")
        pr = next((c, r) for r in range(ROWS) for c in range(COLS) if MAZE[r][c] == "P")
        self.player = Player(*pr)
        gh = [(c, r) for r in range(ROWS) for c in range(COLS) if MAZE[r][c] == "G"]
        self.ghosts = [Ghost(i, *gh[i % len(gh)]) for i in range(4)]
        speed_mult = 1.0 + 0.08 * (self.level - 1)
        self.player.speed = PLAYER_SPEED * speed_mult
        for g in self.ghosts:
            g.speed = GHOST_SPEED * speed_mult
        self.fright_timer = 0.0
        self.ghost_combo = 0
        self.mode = "scatter"
        self.mode_idx = 0
        self.mode_timer = SCATTER_CHASE[0][0]

    # -------------------------------------------------- update

    def update(self, dt, t):
        if self.state in ("title", "gameover", "paused"):
            return
        self.state_timer -= dt
        if self.state == "ready":
            if self.state_timer <= 0:
                self.state = "play"
            return
        if self.state == "dying":
            if self.state_timer <= 0:
                if self.lives <= 0:
                    self.state = "gameover"
                    self.high = max(self.high, self.score)
                else:
                    self.reset_level(full=False)
                    self.state = "ready"
                    self.state_timer = 1.5
            return
        if self.state == "levelup":
            if self.state_timer <= 0:
                self.level += 1
                self.reset_level(full=True)
                self.state = "ready"
                self.state_timer = 1.5
            return

        # ---- play ----
        if self.fright_timer > 0:
            self.fright_timer -= dt
            if self.fright_timer <= 0:
                self.ghost_combo = 0
                for g in self.ghosts:
                    if g.state == "frightened":
                        g.state = "normal"
                        g.speed = GHOST_SPEED * (1.0 + 0.08 * (self.level - 1))
        else:
            self.mode_timer -= dt
            if self.mode_timer <= 0:
                if self.mode == "scatter":
                    self.mode = "chase"
                    self.mode_timer = SCATTER_CHASE[min(self.mode_idx, 3)][1]
                else:
                    self.mode = "scatter"
                    self.mode_idx += 1
                    self.mode_timer = SCATTER_CHASE[min(self.mode_idx, 3)][0]
                for g in self.ghosts:
                    if g.state == "normal":
                        g.dir = (-g.dir[0], -g.dir[1])

        self.player.update(dt)
        for g in self.ghosts:
            g.update(dt, self)

        # eat pellets
        pc, pr = int(round(self.player.x)), int(round(self.player.y))
        if (pc, pr) in self.pellets:
            self.pellets.remove((pc, pr))
            self.score += 10
            self.chomp_alt = not self.chomp_alt
            self.sounds.play("chomp" if self.chomp_alt else "chomp2")
        if (pc, pr) in self.powers:
            self.powers.remove((pc, pr))
            self.score += 50
            self.fright_timer = max(2.5, FRIGHT_TIME - 0.5 * (self.level - 1))
            self.ghost_combo = 0
            self.sounds.play("power")
            for g in self.ghosts:
                g.set_frightened()

        # collisions
        for g in self.ghosts:
            if g.state in ("home", "leaving", "eyes"):
                continue
            if (g.x - self.player.x) ** 2 + (g.y - self.player.y) ** 2 < 0.45:
                if g.state == "frightened":
                    g.set_eaten()
                    self.ghost_combo += 1
                    self.score += 200 * (2 ** (self.ghost_combo - 1))
                    self.sounds.play("eat_ghost")
                elif self.player.airborne:
                    continue  # leap clear over the TIE fighter
                else:
                    self.lives -= 1
                    self.sounds.play("death")
                    self.state = "dying"
                    self.state_timer = 1.6
                    return

        if not self.pellets and not self.powers:
            self.sounds.play("win")
            self.state = "levelup"
            self.state_timer = 2.0

    # -------------------------------------------------- draw

    def draw(self, t):
        s = self.screen
        s.fill(SPACE)
        draw_starfield(s, self.stars, t)

        if self.state == "title":
            self.draw_title(t)
            return

        draw_maze(s)
        for (c, r) in self.pellets:
            draw_pellet(s, c, r, t)
        for (c, r) in self.powers:
            draw_power(s, c, r, t)

        for g in self.ghosts:
            draw_ghost(s, g, t, self.fright_timer)
        if self.state == "dying":
            # explosion
            x, y = self.player.pixel_pos()
            prog = 1.6 - self.state_timer
            for i in range(10):
                a = i * 0.628 + prog
                rr = int(prog * 30)
                pygame.draw.circle(s, (255, 160 + random.randrange(60), 40),
                                   (int(x + math.cos(a) * rr), int(y + math.sin(a) * rr)), max(1, 5 - int(prog * 3)))
        else:
            draw_player(s, self.player, t, self.fright_timer)

        # HUD
        s.blit(self.font.render(f"SCORE  {self.score}", True, YELLOW), (16, 12))
        s.blit(self.font.render(f"HIGH  {max(self.high, self.score)}", True, GREY), (16, 40))
        lvl = self.font.render(f"SECTOR {self.level}", True, WALL_EDGE)
        s.blit(lvl, (WIDTH - lvl.get_width() - 16, 12))
        for i in range(self.lives - 1):
            fake = Player(0, 0)
            fake.x = (WIDTH - 30 - i * 34) / TILE - 0.5
            fake.y = (44 - HUD_H) / TILE - 0.5
            fake.dir = RIGHT
            draw_player(s, fake, 0, 0)

        if self.state == "ready":
            self.center_text("MAY THE FORCE BE WITH YOU", YELLOW)
        elif self.state == "paused":
            self.center_text("PAUSED", WHITE)
        elif self.state == "gameover":
            self.center_text("THE FORCE IS NOT WITH YOU", (255, 80, 80))
            msg = self.font.render("PRESS ENTER TO TRY AGAIN", True, WHITE)
            s.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 + 30))
        elif self.state == "levelup":
            self.center_text("SECTOR CLEARED!", (120, 255, 120))

    def center_text(self, text, color):
        img = self.big_font.render(text, True, color)
        bg = pygame.Surface((img.get_width() + 24, img.get_height() + 12))
        bg.fill(SPACE)
        bg.set_alpha(210)
        x = WIDTH // 2 - img.get_width() // 2
        y = HEIGHT // 2 - 10
        self.screen.blit(bg, (x - 12, y - 6))
        self.screen.blit(img, (x, y))

    def draw_title(self, t):
        s = self.screen
        title = self.big_font.render("P A C - W A R S", True, YELLOW)
        s.blit(title, (WIDTH // 2 - title.get_width() // 2, 110))
        sub = self.font.render("A PAC-MAN STORY FROM A GALAXY FAR, FAR AWAY", True, GREY)
        s.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 170))

        lines = [
            ("Pilot your X-WING through the Death Star.", WHITE),
            ("Collect every energy cell.", WHITE),
            ("Grab a DEATH STAR CORE to ignite your", WHITE),
            ("lightsaber and strike down TIE fighters!", WHITE),
            ("", WHITE),
            ("VADER hunts you.  BOBA cuts you off.", (210, 40, 40)),
            ("MAUL flanks you.  TROOPER panics.", (200, 70, 200)),
        ]
        y = 250
        for txt, col in lines:
            if txt:
                img = self.font.render(txt, True, col)
                s.blit(img, (WIDTH // 2 - img.get_width() // 2, y))
            y += 34

        # demo ships
        fake = Player(0, 0)
        fake.x, fake.y = 4.0, (520 - HUD_H) / TILE - 0.5
        fake.dir = RIGHT
        draw_player(s, fake, t, 1 if int(t) % 4 < 2 else 0)
        for i in range(4):
            g = Ghost(i, 0, 0)
            g.x = 8.0 + i * 2.2
            g.y = (520 - HUD_H) / TILE - 0.5
            g.state = "normal"
            draw_ghost(s, g, t, 0)

        if int(t * 2) % 2 == 0:
            p = self.big_font.render("PRESS ENTER", True, WHITE)
            s.blit(p, (WIDTH // 2 - p.get_width() // 2, 580))
        ctrl = self.font.render("ARROWS / WASD TO MOVE   P = PAUSE   ESC = QUIT", True, GREY)
        s.blit(ctrl, (WIDTH // 2 - ctrl.get_width() // 2, 640))

    # -------------------------------------------------- input

    def key(self, k):
        if k in (pygame.K_UP, pygame.K_w):
            self.player.want = UP
        elif k in (pygame.K_DOWN, pygame.K_s):
            self.player.want = DOWN
        elif k in (pygame.K_LEFT, pygame.K_a):
            self.player.want = LEFT
        elif k in (pygame.K_RIGHT, pygame.K_d):
            self.player.want = RIGHT
        elif k == pygame.K_p and self.state in ("play", "paused"):
            self.state = "paused" if self.state == "play" else "play"
        elif k == pygame.K_SPACE and self.state == "play":
            if self.player.jump():
                self.sounds.play("jump")
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if self.state == "title":
                self.start_game()
            elif self.state == "gameover":
                self.score = 0
                self.lives = 3
                self.level = 1
                self.reset_level(full=True)
                self.start_game()

    def start_game(self):
        self.state = "ready"
        self.state_timer = 2.0 + (3.2 if self.sounds.ok else 0)
        if self.sounds.ok:
            delay = 0
            for snd, dur in self.sounds.march:
                # schedule via simple list the main loop drains
                self.pending_notes.append((pygame.time.get_ticks() + delay * 1000, snd))
                delay += dur

    pending_notes = []


# ---------------------------------------------------------------- main

def main():
    pygame.init()
    sounds = SoundBank()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("PAC-WARS")
    font = pygame.font.SysFont("consolas", 20, bold=True)
    big_font = pygame.font.SysFont("consolas", 32, bold=True)
    clock = pygame.time.Clock()
    game = Game(screen, sounds, font, big_font)

    frames = None
    if "--smoke-test" in sys.argv:
        frames = 180
        game.key(pygame.K_RETURN)

    t = 0.0
    while True:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        t += dt
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                game.key(ev.key)

        now = pygame.time.get_ticks()
        for item in list(game.pending_notes):
            when, snd = item
            if now >= when:
                snd.play()
                game.pending_notes.remove(item)

        game.update(dt, t)
        game.draw(t)
        pygame.display.flip()

        if frames is not None:
            frames -= 1
            if frames <= 0:
                # exercise some input paths, then quit
                pygame.quit()
                return


if __name__ == "__main__":
    main()
