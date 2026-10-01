# Swarm Bot (Roblox)

Plays the Roblox arcade swarm game for you: it looks at the **Roblox window**, dodges bullets and mobs
with **Z Q S D** (the W A S D key positions, so AZERTY works), aims with the mouse and holds **Space** to shoot.

## Download
https://github.com/FeniksRevenge/Eindwerk/releases/latest/download/SwarmBot.exe

Put it in its own folder and double-click it (Windows may say "unknown publisher": More info -> Run anyway).
It keeps its settings (`config.json`) and pictures (`pictures/`) next to itself.

## Use
1. Open the game in Roblox (windowed is fine, any size, anywhere on the screen) and start a run.
2. Press **`*`** (or Start). Press **`-`** to stop.
3. It stops by itself at the GAME OVER screen, or with **Auto restart** on, clicks **PLAY AGAIN** and keeps
   going (it waits for the countdown).

| Key | What |
|---|---|
| `*` | start |
| `-` | stop |
| `/` | save a screenshot of what it sees (`pictures/shot_..._bot.png` shows what it detected) |
| `+` | save the **last 8 seconds** (`pictures/rec_...`): zip that folder and send it when it does something dumb |

It only presses keys while the Roblox window is in front (setting), and it takes over your mouse while running.

## How it works
- `winio.py`: finds the window titled "Roblox", screenshots its inside, presses keys by physical position.
- `vision.py`: finds you (the white UFO + its gray ball) and every enemy by color and size. Sizes are relative
  to the window height, so any window size works. Ignores the HUD, chat (its sun emojis), the wave banner,
  floating score text and the boss health bar.
- `tracker.py`: follows things between screenshots to know their speed and direction.
- `planner.py`: tries 81 short move plans (0.75 s ahead), predicts bullets (straight lines) and mobs (walking
  at you; grunts a bit slower than you, tiny tanks faster, tanks/yellow slower, the boss can rush) and picks
  the plan that never gets hit and keeps the most room, away from walls, corners and crowds. Aims at yellow
  mobs first, then orange shooters, then whatever is closing in, ahead of where they're going.
- `runner.py`: the loop; measures your speed and the game's input delay while playing and plans from where
  you'll really be when its keys land. GAME OVER screen and auto restart.
- `tests/fakegame.py`: a fake version of the game built from screenshot pieces, with the real rules, used to
  test the whole bot (`python tests/fakegame.py 60 3 0.12` = 3 games of 60 s with 0.12 s input delay).

Automating Roblox is against Roblox's Terms of Use; using this can get the account banned.
