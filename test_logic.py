"""Headless gameplay exercise: simulate ~60s of play with random inputs."""
import os
import random

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pacwars

pygame.init()
sounds = pacwars.SoundBank()
screen = pygame.display.set_mode((pacwars.WIDTH, pacwars.HEIGHT))
font = pygame.font.SysFont("consolas", 20)
game = pacwars.Game(screen, sounds, font, font)

game.state = "play"
dt = 1 / 60
keys = [pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT]
random.seed(42)

start_pellets = len(game.pellets)
deaths = 0
for frame in range(60 * 120):
    if frame % 20 == 0:
        game.key(random.choice(keys))
    game.update(dt, frame * dt)
    game.draw(frame * dt)
    if game.state == "gameover":
        deaths += 1
        game.key(pygame.K_RETURN)
        game.state = "play"
    elif game.state in ("ready", "dying", "levelup"):
        game.state_timer = 0  # fast-forward transitions
        game.update(dt, frame * dt)
        if game.state == "ready":
            game.state = "play"

# force the power-pellet / frightened / eat-ghost path deterministically
game.state = "play"
game.lives = 3
for g in game.ghosts:
    g.x, g.y = float(g.home[0]), float(g.home[1])  # move ghosts away from player
game.player.x = float(round(game.player.x))
game.player.y = float(round(game.player.y))
game.powers.add((int(game.player.x), int(game.player.y)))
game.update(dt, 0)
assert game.fright_timer > 0, "power pellet should trigger frightened mode"
g = game.ghosts[0]
g.state = "frightened"
g.x, g.y = game.player.x, game.player.y
game.update(dt, 0)
assert g.state == "eyes", "frightened ghost should be eaten on contact"
# let the eyes find their way home
for frame in range(60 * 30):
    game.update(dt, frame * dt)
    if g.state in ("home", "leaving", "normal", "frightened"):
        break
assert g.state in ("home", "leaving", "normal", "frightened"), f"eyes never got home: {g.state}"

# force the level-clear path
game.pellets.clear()
game.powers.clear()
game.state = "play"
game.update(dt, 0)
assert game.state == "levelup", "clearing all pellets should end the level"

print(f"OK: simulated 2 min, ate {start_pellets - len(game.pellets)} of {start_pellets} pellets, "
      f"{deaths} game-overs, score {game.score}, eyes-home and level-clear paths verified")
