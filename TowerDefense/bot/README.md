# Swarm screen bot (Roblox)

Plays the Roblox arcade swarm game for you by reading your screen and pressing keys like a person:
it holds WASD to dodge, moves the mouse to aim and holds **Space** to shoot (switchable to left click in the app).

- **`*`** starts it (Shift+8 or numpad `*`)
- **`-`** stops it
- **`/`** saves a screenshot of what the bot sees (you keep playing; see below)
- It keeps playing until you die: it **stops by itself when the GAME OVER screen appears** (dark red background
  with the score panel). As a backup it also stops if it can't see you at all for 30 seconds (setting).
- **Auto restart** (setting, off by default): after a game over it waits ~1 s for the GAME OVER screen to
  finish appearing, clicks **PLAY AGAIN** and keeps playing (up to 3 clicks, 3 s apart). If that doesn't
  work it stops, logs what it measured and saves a screenshot. **Test PLAY AGAIN** (next to the setting):
  switch to Roblox with the GAME OVER screen showing; 3 s later it checks the screen, logs what it found and
  clicks the button.
- It only sends keys/mouse while the **Roblox window is in front**, so it won't type into other apps

Windows only.

## Download (no Python needed)
Get **SwarmBot.exe** from the latest release:
https://github.com/FeniksRevenge/Eindwerk/releases/latest/download/SwarmBot.exe

Put it in its own folder (it saves `config.json` next to itself) and double-click it.
Windows may warn that it's from an unknown publisher: click **More info → Run anyway**.

The exe is built automatically by GitHub Actions (`.github/workflows/build-swarm-bot.yml`) whenever
the bot code changes.

## Running from source instead
1. Install Python: open CMD and run `winget install Python.Python.3.12`, then close and reopen CMD.
2. Download this `bot` folder (all files) somewhere, e.g. `C:\Users\super\swarm-bot`.
3. Double-click `start_app.bat`.

## The app
Double-click **SwarmBot.exe** (or `start_app.bat` when running from source). It opens the Swarm Bot window with:
- **Start / Stop** buttons (same as the `*` and `-` hotkeys, which keep working while you're in Roblox)
- the bot's status (Running / Stopped (died) / Waiting for the player) and its speed in fps
- **Fast screen capture (dxcam)**: on by default; untick it if the bot can't find you (see below)
- **Calibrate everything**, **Test view** and **Redo one** (recalibrate just the boss, a bullet, ...)
- settings: only control Roblox when it's the active window, how long it may not see you before it stops
  anyway (backup; it normally stops at the GAME OVER screen), and color tolerance
- a log of what happened

## Quick setup (no clicking)
1. Put Roblox on your **main screen** (the bot only looks at the main screen, all of it, top to bottom).
2. Click **Use preset colors**: colors and sizes measured from real screenshots and close-ups of every
   enemy. It's also a **reset**: it replaces all learned colors and empties the "not a thing" list. If you
   use the preset, newer versions of the preset are picked up automatically.
3. Click **Test view** to check everything gets circled.

If the preset doesn't match (different graphics settings), calibrate yourself:
**Calibrate from screenshots...** lets you pick **one or more** screenshots you saved with `/` (Ctrl/Shift-click
to select several) and click things on each: **S** = skip this thing, **N** = next photo, **Esc** = finish.
Each thing's color and size is the **average of all your clicks** over all photos.

## Calibrate (once, or again if colors/sizes change)
Click **Calibrate everything** in the app (or double-click `calibrate.bat`).
1. Start the game in Roblox. Try to have a basic mob, an orange shooter, a bullet and ideally the boss on screen; press **P** to pause there.
2. Press Enter in the calibration window, switch to Roblox within 5 seconds. It takes a screenshot of the main screen.
3. Click on each thing it asks for. Press **S** to skip something that isn't on screen, **R** to redo a click.
   It asks for, in order: the **gray ball** (you), a **red bullet** (boss), an **orange bullet** (shooter),
   a **yellow mob's bullet**, the **red square** (basic mob), the **orange ball** (shooter, not its ring),
   the **yellow mob** (shoots in all directions), a **purple tank**, one of the **tiny mobs** a dead tank
   splits into, the **red cross** (boss) and a **green health circle**.

The bot walks over green health circles when it's safe to, and dodges both red and orange bullets.
An orange ball **inside a ring** is a shooter, and its danger size is the whole ring; an orange ball
**without a ring** is a bullet. (Same in Test view, the screenshots and the photo trainer.)
It still finds you behind the see-through **health bar** and **score** panels, and when it briefly can't see
you at all (behind a mob) it keeps playing from where you should be for up to 1.5 seconds.

The bot always looks at your **whole main screen**, also with Windows display scaling (125%, 150%, ...).
The log shows the screen size it uses when the app starts.

**Click on the solid, colored middle of each thing** (not a thin ring or outline). Clicks on the background
are refused. **Close Roblox chat** (chat icon, top left) before botting: its emoji icons look like bullets.

Missed the boss? Use **Redo one → boss** in the app later with the boss on screen (keeps everything else).

## Check it
Click **Test view** in the app (or `test_view.bat`) while the game runs. A window shows circles around everything the bot sees,
without it touching your keyboard or mouse. Press Q to close it.
If something isn't circled, or wrong things are, calibrate that thing again.

## Run
Go to Roblox, start a run and press **`*`** (or click Start). Press **`-`** to stop.

## Simulator (watch the bot play and train)
Click **Simulator** in the app. The bot's **real brain** plays a practice arena (orange shooters, yellow
mobs shooting in all directions, grunts, purple tanks that **split into 3 tiny mobs** when they die, the
boss with its bullet rings), with the same reaction delay as in Roblox. Your player shoots back.

- **HP bar 10/10**: every hit costs 1 HP. Killed mobs sometimes (5%) drop a **green circle**: walking over
  it gives **+2 HP**. It gets harder over time (an extra enemy every 15 s), like real waves.
- **1x / 2x / 5x / 10x / 100x** speed, **Pause**, **Restart**, and a scenario list (Mixed, Many shooters, Boss, Swarm).
  At 100x it runs as fast as your PC can; the info line shows the real speed (e.g. `running at 40x`).
- **Keep training while it plays** (on by default): training runs nonstop in the background while you
  watch, on at most half your CPU cores (max 4) and at low priority, so the game and the real bot always
  come first. Each round plays 4 test fights with the current dodge settings and with a
  bunch of small changes (more changes on PCs with more cores), all at once at full speed, and keeps the
  best change if it survives more than 3% longer. Better settings are used **right away**, also by the fight
  you're watching. When the player reaches **0/10** it just plays again. **Reset training** goes back to
  the defaults.
- The trained settings are saved in `config.json` (`brain_params`) and **the real bot uses them too**.
  When the dodging logic changes a lot in a new version, older training is ignored and it starts fresh.
- The **Boss** scenario is a boss wave like in the game: only the boss, which summons 3 grunts every 8 s
  and shoots bullet rings and aimed shots.

## It can't find me (the gray ball)
- If the bot doesn't see you within 3 seconds of pressing `*`, it **saves a screenshot automatically** and
  says so in the log. Open the `_bot.png` (**Open screenshots folder**): is your ball circled in white?
- Not circled, and the picture looks wrong (black, other screen, washed-out colors)? Untick **Fast screen
  capture (dxcam)** in the app. (The bot already compares dxcam with a normal screenshot at start and
  switches by itself when they differ; the log says which one it uses.)
- Picture is fine but you're not circled: click **Use preset colors** (a wrong click in the photo trainer
  can shift the learned gray), or **Clear ignore list**. The player can't be put on the ignore list
  anymore, and when the learned gray finds nothing the bot also tries the preset gray.

## Overlay (see what the bot sees on your screen)
Tick **Show overlay on screen** in the app. While the bot runs, it draws right on top of the game at 60 fps
(between the bot's own updates everything glides along its measured speed):
cyan circles around everything it detects (with labels), a white circle and **YOU** on your player,
the aim line, and an arrow for the keys it's holding; a line at the bottom counts what it sees.
The overlay is click-through and hidden from screen capture, so the bot never sees its own drawings.

## Photo trainer (teach it from screenshots)
Press **`/`** while playing to save screenshots, then train on them in the app (**PHOTO TRAINER**).
It opens every photo one after another and shows what the bot detected. Each finished photo is
deleted (with its `_bot.png` and `.json`).

**Train on photos (ask me)**: you check each photo.
| Key / click | Meaning |
|---|---|
| **Enter** | the bot's answer is right: learn from it, next photo |
| **click a circle** | it's wrong: pick what it really is (a–k), or **x** = not a thing (ignored from now on) |
| **click something without a circle** | the bot missed it: pick what it is |
| **U** | undo your last correction |
| **S** | skip this photo (it's kept) |
| **Esc** | stop (the current photo is kept) |

Bullets, mobs and health circles can't be put on the ignore list (an old entry that matches one of them is
not applied), so a wrong X can never make the bot blind to them.

Gray crossed-out circles are things on the **ignore list** (you once said "not a thing"). If one of them
*is* a thing, click it and pick what it is: it's taken off the ignore list and learned. **Clear ignore
list** in the app empties the whole list at once. When you click, the smallest circle under the mouse is
picked, so a bullet right next to a shooter's ring gets the bullet.

**Train on photos (auto)**: goes through all photos by itself and only learns from detections that
already match well, so your real colors and sizes slowly replace the preset ones.

What it learns (colors, sizes, and the "not a thing" list) is saved in `config.json`.

## Screenshots (`/`)
Press **`/`** (or numpad `/`) anytime, with the bot running or not. Nothing pauses: it saves into the
`screenshots` folder next to SwarmBot.exe (**Open screenshots folder** in the app):
- `shot_<time>.png`: the play area as the bot captured it
- `shot_<time>_bot.png`: the same with everything the bot detected circled, a white circle on what it
  thinks is **you**, the keys it's holding (top bar) and a yellow line to where it's aiming
- `shot_<time>.json`: the same info as numbers

If the bot misbehaves (e.g. keeps running to one side), send these; they show exactly what it saw.

While the bot runs it also takes a photo **automatically every 10 seconds**. Turn this on/off with
**Take pictures automatically while the bot plays** in the app, and set how often with **Picture every
(seconds)**. It stops adding automatic photos once 300 are waiting. Train on them afterwards with the photo trainer.

## Tuning (`config.json`, created by calibrate)
| Setting | What it does |
|---------|--------------|
| `tolerance` | How close a color must be, `[L, a, b]`. Raise if things aren't found, lower if random stuff is. |
| `downscale` | 2 = look at half resolution (faster). 1 = full resolution (more accurate, slower). |
| `death_timeout` | Backup: seconds it may not see you before it stops anyway (at least 20). It normally stops at the GAME OVER screen. |
| `require_focus` | `true` = only send input while Roblox is the active window. |
| `auto_restart` | `true` = click PLAY AGAIN after a game over and keep playing. |
| `fast_capture` | `true` = fast dxcam capture (checked against a normal screenshot at start), `false` = always mss. |
| `fire_with` | `"space"` (default) or `"mouse"` (hold left click) to shoot. |
| `expand` | Danger size per kind, e.g. `{"boss": 1.5}`: the bot treats it as 1.5x bigger and keeps more distance. Set it in the app under **Danger size of**. |

## Speed
- Screenshots are taken non-stop on their own thread with Windows' fast **Desktop Duplication** capture
  (`dxcam`; falls back to `mss`), so the bot always works on the freshest frame. The fps display in the
  app shows which one is used, e.g. `30 fps (dxcam)`.
- Detection takes ~9 ms per frame on a 2534x1239 screen (was ~22 ms, and ~50-75 ms before that): one quick
  pass finds where there is anything at all (the game is black), and only those spots are looked at, with a
  color table built once instead of checking every color over the whole screen.
- Screenshots are only taken when the bot is ready for the next one (not non-stop), so capturing doesn't
  keep a CPU core busy.
- The brain leaves out bullets and mobs that can't reach you within its 0.8 s look-ahead (exactly the same
  decisions, about 30% less work).
- The bot plans from where you'll be when its keys land, so its reaction delay is accounted for.

## Danger priority
- It **shoots yellow mobs first** (they shoot in all directions), then **orange shooters**, unless something
  else is about to reach you.
- It also keeps a bit more distance from them when choosing where to go: yellow 1.6x, orange 1.3x, the
  boss 3.6x as much as a normal mob.
- The yellow mob's danger size is its **ring**, like the orange shooter's.

## Health circles
It goes for green health circles (+2 HP), also during a boss fight unless the circle is right next to the
boss: picking one up on the way counts as a big reward in its planning, and it heads toward the nearest
one. In the simulator it collects about twice as many as before, for slightly more near misses.

## Dodging
- The planner checks the **closest approach during each time step**, not only at sampled moments, so a fast
  bullet coming straight at you can't slip "through" between two checks. In the simulator this halved the
  hits (3.0 -> 1.5 per minute with the bot's perfect view).
- Anything that flies at bullet speed is dodged like a bullet, whatever it was taken for (two red bullets
  touching can look like a grunt); touching bullets are reported as one bullet-sized danger.
- A kind of thing you never calibrated (e.g. the yellow mob's bullets) uses the preset colors instead of
  being invisible.

## Floating text
Score popups like **+10 / +25** in red, orange, purple, yellow or gray are ignored: a row of bullet-sized
pieces where at least one isn't a round ball (a "1", a "+", a "2") is text. A lone "+" is too thin to be a
bullet. Rows of real things are kept: bullets are round, and the **3 tiny tanks** a dead tank splits into
are bigger than bullets.

## Relearn the player / what it knows
- **Relearn the player** (main window): press Enter in the calibration window, switch to Roblox, and click on
  yourself in the screenshot. Do this whenever your look changes. The **old look is kept**, so both keep
  working (and the photo trainer never mixes two looks into one).
- **What it knows...** lists everything the bot recognizes: the player and all its looks, every bullet and
  mob, the health circle, with their color, size, where it was learned (preset, calibration, number of
  photo-trainer examples), danger size, and the **ignore list**. Select a row to:
  **Relearn** it (screenshot now, or from saved screenshots), **Reset to preset**, **Make main look** (for a
  player look), or **Remove** it (a player look, an ignore entry, or a thing).

## Standing still / not recognized for a moment
Every time the bot recognizes you it keeps a small picture of you. If it suddenly can't recognize you (standing
still, a hit flash, half behind something), it checks whether that picture is still at your spot and keeps
playing from there (up to 15 s at a time). The first time in a run it really loses you for 1 second it saves
a screenshot and says so in the log: send it if you were actually there.

## Your player's look
The bot knows both looks of your player: the **gray ball** (with its white shield) and the **white UFO**
(a white ball on an oval with black windows), at any angle: tilted while moving or level while standing
still. No recalibration needed when you switch.

## How it works
- `vision.py` finds things by color, tells same-colored things apart by size (red square = mob,
  small red circle = bullet, huge red cross = boss) and tracks them between frames to get their speed.
- `brain.py` tries all 8 WASD directions plus standing still, simulates the next ~0.8 s (including a
  follow-up move) and picks the one that stays furthest from bullets, mobs and walls. It aims at the
  most urgent mob and leads the shot.
- `runner.py` ties it together; `swarm_bot.py` does the Windows screen capture, input and hotkeys.

Automating Roblox is against Roblox's Terms of Use, so using this can get the account banned.
