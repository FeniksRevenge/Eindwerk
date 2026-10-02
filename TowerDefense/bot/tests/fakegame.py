"""The fake game lives in ../fakegame.py (the app also uses it to practice). This runs it:

    python tests/fakegame.py [seconds] [seeds] [input delay] [boss]
"""

import os
import runpy
import sys

BOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT)

if __name__ == "__main__":
    runpy.run_path(os.path.join(BOT, "fakegame.py"), run_name="__main__")
