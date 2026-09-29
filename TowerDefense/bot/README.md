# Swarm screen bot (Roblox)

Plays the Roblox arcade swarm game for you by reading your screen and pressing keys like a person:
it holds WASD to dodge, moves the mouse to aim and holds left click to shoot.

- **`*`** starts it (Shift+8 or numpad `*`)
- **`-`** stops it
- It **stops by itself** when your player disappears (you died)
- It only sends keys/mouse while the **Roblox window is in front**, so it won't type into other apps

Windows only.

## One-time setup
1. Install Python: open CMD and run `winget install Python.Python.3.12`, then close and reopen CMD.
2. Download this `bot` folder (all files) somewhere, e.g. `C:\Users\super\swarm-bot`.

## Calibrate (once, or again if colors/sizes change)
Double-click **`calibrate.bat`**.
1. Start the game in Roblox. Try to have a basic mob, an orange shooter, a bullet and ideally the boss on screen; press **P** to pause there.
2. Press Enter in the black window, switch to Roblox within 5 seconds. It takes a screenshot.
3. Drag a box around the **play area** (the whole game screen) and press Enter.
4. Click on each thing it asks for. Press **S** to skip something that isn't on screen, **R** to redo a click.
   Click the **gray ball** for the player, the **red square** for the basic mob, a **red circle** for the bullets,
   the **orange ball** (not the ring) for the shooter, and the **red cross** for the boss.

Missed the boss? Run `py swarm_bot.py calibrate boss` later with the boss on screen (keeps everything else).

## Check it
Double-click **`test_view.bat`** while the game runs. A window shows circles around everything the bot sees,
without it touching your keyboard or mouse. Press Q to close it.
If something isn't circled, or wrong things are, calibrate that thing again.

## Run
Double-click **`run_bot.bat`**, go to Roblox, start a run and press **`*`**. Press **`-`** to stop.

## Tuning (`config.json`, created by calibrate)
| Setting | What it does |
|---------|--------------|
| `tolerance` | How close a color must be, `[L, a, b]`. Raise if things aren't found, lower if random stuff is. |
| `downscale` | 2 = look at half resolution (faster). 1 = full resolution (more accurate, slower). |
| `death_timeout` | Seconds the player must be missing before it counts as dead and stops. |
| `require_focus` | `true` = only send input while Roblox is the active window. |

## How it works
- `vision.py` finds things by color, tells same-colored things apart by size (red square = mob,
  small red circle = bullet, huge red cross = boss) and tracks them between frames to get their speed.
- `brain.py` tries all 8 WASD directions plus standing still, simulates the next ~0.8 s (including a
  follow-up move) and picks the one that stays furthest from bullets, mobs and walls. It aims at the
  most urgent mob and leads the shot.
- `runner.py` ties it together; `swarm_bot.py` does the Windows screen capture, input and hotkeys.

Automating Roblox is against Roblox's Terms of Use, so using this can get the account banned.
