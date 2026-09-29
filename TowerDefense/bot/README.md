# Swarm screen bot (Roblox)

Plays the Roblox arcade swarm game for you by reading your screen and pressing keys like a person:
it holds WASD to dodge, moves the mouse to aim and holds **Space** to shoot (switchable to left click in the app).

- **`*`** starts it (Shift+8 or numpad `*`)
- **`-`** stops it
- **`/`** saves a screenshot of what the bot sees (you keep playing; see below)
- It keeps playing until you die: it **stops by itself** once your player has been gone for 4 seconds
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
- **Calibrate everything**, **Test view** and **Redo one** (recalibrate just the boss, a bullet, ...)
- settings: only control Roblox when it's the active window, how long the player must be gone
  before it counts as dead, and color tolerance
- a log of what happened

## Quick setup (no clicking)
1. Click **Use preset colors**: colors and sizes measured from real screenshots of the game.
2. Click **Set play area**: press Enter, switch to Roblox, and after 5 seconds drag a box around the game.
3. Click **Test view** to check everything gets circled.

If the preset doesn't match (different graphics settings), calibrate yourself:
**Calibrate from screenshot...** lets you pick a screenshot you saved with `/` and click each thing on it,
so you don't have to catch mobs live.

## Calibrate (once, or again if colors/sizes change)
Click **Calibrate everything** in the app (or double-click `calibrate.bat`).
1. Start the game in Roblox. Try to have a basic mob, an orange shooter, a bullet and ideally the boss on screen; press **P** to pause there.
2. Press Enter in the calibration window, switch to Roblox within 5 seconds. It takes a screenshot.
3. Drag a box around the **play area** (the whole game screen) and press Enter.
4. Click on each thing it asks for. Press **S** to skip something that isn't on screen, **R** to redo a click.
   It asks for, in order: the **gray ball** (you), a **red bullet** (boss), an **orange bullet** (shooter),
   a **yellow mob's bullet**, the **red square** (basic mob), the **orange ball** (shooter, not its ring),
   the **yellow mob** (shoots in all directions), a **purple tank**, one of the **tiny mobs** a dead tank
   splits into, the **red cross** (boss) and a **green health circle**.

The bot walks over green health circles when it's safe to, and dodges both red and orange bullets.

**Click on the solid, colored middle of each thing** (not a thin ring or outline). Clicks on the background
are refused. **Close Roblox chat** (chat icon, top left) before botting: its emoji icons look like bullets.

Missed the boss? Use **Redo one → boss** in the app later with the boss on screen (keeps everything else).

## Check it
Click **Test view** in the app (or `test_view.bat`) while the game runs. A window shows circles around everything the bot sees,
without it touching your keyboard or mouse. Press Q to close it.
If something isn't circled, or wrong things are, calibrate that thing again.

## Run
Go to Roblox, start a run and press **`*`** (or click Start). Press **`-`** to stop.

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

While the bot runs it also takes a photo **automatically every 10 seconds** (setting in the app, 0 = off;
it stops adding automatic photos once 300 are waiting). Train on them afterwards with the photo trainer.

## Tuning (`config.json`, created by calibrate)
| Setting | What it does |
|---------|--------------|
| `tolerance` | How close a color must be, `[L, a, b]`. Raise if things aren't found, lower if random stuff is. |
| `downscale` | 2 = look at half resolution (faster). 1 = full resolution (more accurate, slower). |
| `death_timeout` | Seconds the player must be missing before it counts as dead and stops (at least 3). |
| `require_focus` | `true` = only send input while Roblox is the active window. |
| `fire_with` | `"space"` (default) or `"mouse"` (hold left click) to shoot. |

## How it works
- `vision.py` finds things by color, tells same-colored things apart by size (red square = mob,
  small red circle = bullet, huge red cross = boss) and tracks them between frames to get their speed.
- `brain.py` tries all 8 WASD directions plus standing still, simulates the next ~0.8 s (including a
  follow-up move) and picks the one that stays furthest from bullets, mobs and walls. It aims at the
  most urgent mob and leads the shot.
- `runner.py` ties it together; `swarm_bot.py` does the Windows screen capture, input and hotkeys.

Automating Roblox is against Roblox's Terms of Use, so using this can get the account banned.
