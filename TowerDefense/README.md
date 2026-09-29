# Tower Defense Shooter

Mobs walk the path toward your base. Shoot them yourself and build towers with the gold you earn.
One hit kills you (touching a mob or a mob bullet). Game also ends if the base drops to 0 HP.

## Run
```
pip install -r requirements.txt
python tower_defense.py
```

## Controls
| Key | Action |
|-----|--------|
| WASD | Move |
| Mouse | Aim |
| Left mouse (hold) | Shoot |
| 1 / 2 | Select Gun / Cannon tower |
| Right mouse | Place selected tower |
| Space | Start next wave early |
| P / Esc | Pause |
| R | Restart after game over |

## Mobs
- **Grunt** (red) - basic
- **Runner** (yellow) - fast, from wave 2
- **Shooter** (cyan) - shoots at you, from wave 3
- **Tank** (purple) - lots of HP, costs the base 2 HP, from wave 4
