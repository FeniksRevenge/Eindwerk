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
   going (it waits for the countdown). **Games to play**: how many games to play after Start, then stop
   (blank = keep going).

| Key | What |
|---|---|
| `*` | start |
| `-` | stop |
| `/` | save a screenshot of what it sees (`pictures/shot_..._bot.png` shows what it detected) |
| `+` | save the **last 8 seconds** (`pictures/rec_...`): zip that folder and send it when it does something dumb |

It only presses keys while the Roblox window is in front (setting), and it takes over your mouse while running.

## Overnight: it gets better run after run
Turn on **Auto restart**, start a run and press `*`. It keeps playing game after game, and it learns
(remembered in `learned.json` next to the app; **Reset learning** forgets it):
- **What hit you:** when the screen flashes red (you got hit) it looks at what was closest and keeps a bit more
  room from that kind of enemy (going back to normal when that kind stops hitting you).
- **Measuring instead of guessing:** enemy speeds, the speed of each bullet color, your own speed and the
  game's input delay are measured every run and remembered, so new enemies and bullets are predicted
  right from the start. At every hit by a bullet or small enemy it also works out how big your hitbox
  really is (how close that thing really came), and after 6 hits it dodges with that size.
- **Play style, by trying:** after a few normal runs it tries a small change (more/less room from bullets
  or enemies, staying further from walls, running more or fewer laps, avoiding crowds more) for 4 runs and
  keeps it only if those runs lasted clearly longer. Runs differ a lot, so this is slow: think ~10 tries a
  night, and a lucky streak can fool it now and then.
- The window shows the runs so far (average of the last 10, best) and what it's trying.

While it runs, it keeps telling Windows the screen is in use (no sleep, no screen off), and when it has
sent Roblox nothing for a minute (lobby, GAME OVER screen) it wiggles the mouse by 1 pixel over the Roblox
window, so neither Windows nor Roblox thinks you're away. For a whole night also set Windows itself:
Settings > System > Power > Screen and sleep: **Never** (plugged in), and no screen saver. Every hit is saved as a short clip in
`pictures/hits/` (the newest 40): zip that folder and `learned.json` and send them, that's how the bot
gets better the most.

**If you get disconnected or kicked:** it doesn't try to get back to the arcade. When it hasn't seen you or
a GAME OVER screen for 90 s, or the picture hasn't changed for 45 s, or the Roblox window is gone, it lets
go of all keys, saves a screenshot, writes the time in the log and stops.

**Windows HDR:** the fast screen capture (dxcam) gets wrong colors while HDR is on, so when you start the bot it
turns HDR off (the screen flickers once) and turns it back on when you stop the bot or close the app.

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
- `learn.py`: what it learns between runs (see above).
- `runner.py`: the loop; measures your speed and the game's input delay while playing and plans from where
  you'll really be when its keys land. GAME OVER screen and auto restart.
- `tests/tune.py`: tunes all the planner's settings by playing thousands of fast fake games (late waves
  and the boss) and writes the best to `tuned.py` (`python tests/tune.py tune`, then `compare`).
- `tests/calibrate.py`: makes the fake game use the speeds measured in the real game
  (`python tests/calibrate.py learned.json`).
- `tests/fakegame.py`: a fake version of the game built from screenshot pieces, with the real rules, used to
  test the whole bot (`python tests/fakegame.py 60 3 0.12` = 3 games of 60 s with 0.12 s input delay).

Automating Roblox is against Roblox's Terms of Use; using this can get the account banned.
