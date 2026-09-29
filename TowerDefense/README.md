# Swarm Defense

Mobs come in from every side and run straight at you. Orange shooters keep their distance and fire. A boss shows up every 5 waves.
You only have your own gun: no towers, no upgrades. One hit kills you (touching a mob or a mob bullet), and game over is final.

Waves get bigger over time, but mob and boss HP never change.

## Play
Double-click `tower_defense.html`. It runs in the browser, no install needed.

Press **B** to let the bot play for you.

## Controls
| Key | Action |
|-----|--------|
| WASD | Move |
| Mouse | Aim |
| Left mouse (hold) | Shoot |
| B | Turn the bot on/off |
| P / Esc | Pause |

## Mobs
- **Grunt** (red) - basic
- **Runner** (yellow) - fast, from wave 2
- **Shooter** (orange) - runs away when you get close, circles you and shoots, from wave 3
- **Tank** (blue) - lots of HP, from wave 4
- **Boss** (dark red, big) - every 5th wave, fires bullet rings and aimed bursts

## Bot
The bot only moves and shoots, same as you. Every frame it predicts where bullets and mobs will be
over the next ~0.8 seconds, picks the safest direction, and leads its shots.

`tower_defense.py` is an older pygame prototype and does not have these rules (it still has towers and no bot or boss).
