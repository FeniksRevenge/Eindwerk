"""
Makes the fake game match the real one: reads a learned.json from the app (what it measured in the real
game) and writes tests/calibration.json, which the fake game uses for enemy and bullet speeds.

    python tests/calibrate.py path/to/learned.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        d = json.load(f)
    me = d.get("me", {}).get("speed")  # your speed, x window height per second
    cal = {"speed": d.get("speed", {})}
    if me:
        cal["bullet_speed"] = {c: round(v / me, 3) for c, v in d.get("bullet_speed", {}).items()}
    with open(os.path.join(HERE, "calibration.json"), "w") as f:
        json.dump(cal, f, indent=1)
    print("calibration.json:", cal)
    if d.get("body_scale", 1.0) != 1.0:
        print(f"note: the real hitbox measured x{d['body_scale']} the UFO shape (planner.BODY_* to change)")
