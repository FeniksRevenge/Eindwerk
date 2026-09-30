"""
On-screen overlay: draws what the bot detects right on top of the game, live.

A transparent, always-on-top, click-through window over the main screen. It's hidden from screen
capture (Windows 10 2004+), so the bot never sees its own drawings. It draws in cyan, a color the
game doesn't use, so even where capture-hiding isn't available the bot won't mistake it for mobs.
"""

import ctypes
import os
import tkinter as tk

KEY = "#010203"      # this color becomes see-through
INK = "#00e5ff"      # cyan: not a color the game uses
LABELS = {"enemy_bullet": "bullet", "shooter": "shooter", "runner": "yellow", "grunt": "grunt",
          "tank": "tank", "tank_mini": "tiny", "boss": "BOSS", "health": "+hp"}


def _make_click_through(win):
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        user32.SetWindowDisplayAffinity(hwnd, 0x11)  # WDA_EXCLUDEFROMCAPTURE
    except Exception:
        pass


class Overlay:
    def __init__(self, master, region, get_last):
        """region: {"left","top","width","height"} in screen pixels. get_last(): the bot's latest
        tick (dict with dets/player/keys/aim) or None when the bot isn't running."""
        self.get_last = get_last
        self.region = region
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.geometry(f"{region['width']}x{region['height']}+{region['left']}+{region['top']}")
        self.win.configure(bg=KEY)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            self.win.attributes("-alpha", 0.6)  # not Windows: half see-through instead
        self.canvas = tk.Canvas(self.win, width=region["width"], height=region["height"], bg=KEY,
                                highlightthickness=0)
        self.canvas.pack()
        self.win.update_idletasks()
        _make_click_through(self.win)
        self.alive = True
        self.tick()

    def close(self):
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def tick(self):
        if not self.alive:
            return
        try:
            self.draw(self.get_last())
        except Exception:
            pass
        self.win.after(50, self.tick)

    def draw(self, last):
        c = self.canvas
        c.delete("all")
        if not last:
            c.create_text(20, self.region["height"] - 20, anchor="w", fill=INK, font=("Consolas", 12),
                          text="Swarm Bot overlay: waiting for the bot to run (press *)")
            return
        counts = {}
        for name, items in last.get("dets", {}).items():
            if name == "player":
                continue
            for (x, y, r) in items:
                counts[name] = counts.get(name, 0) + 1
                c.create_oval(x - r - 3, y - r - 3, x + r + 3, y + r + 3, outline=INK, width=2)
                if name != "enemy_bullet":
                    c.create_text(x, y - r - 12, text=LABELS.get(name, name), fill=INK, font=("Consolas", 10))
        p = last.get("player")
        if p:
            x, y, r = p
            c.create_oval(x - r - 8, y - r - 8, x + r + 8, y + r + 8, outline="#ffffff", width=3)
            c.create_text(x, y + r + 20, text="YOU", fill="#ffffff", font=("Consolas", 11, "bold"))
            aim = last.get("aim")
            if aim:
                c.create_line(x, y, aim[0], aim[1], fill=INK, dash=(4, 4))
                c.create_line(aim[0] - 10, aim[1], aim[0] + 10, aim[1], fill=INK, width=2)
                c.create_line(aim[0], aim[1] - 10, aim[0], aim[1] + 10, fill=INK, width=2)
            keys = last.get("keys") or ()
            dx = ("d" in keys) - ("a" in keys)
            dy = ("s" in keys) - ("w" in keys)
            if dx or dy:
                n = (dx * dx + dy * dy) ** 0.5
                c.create_line(x, y, x + dx / n * 70, y + dy / n * 70, fill="#ffffff", width=4, arrow="last")
        summary = "  ".join(f"{LABELS.get(k, k)}:{v}" for k, v in sorted(counts.items()))
        keys = "".join(last.get("keys") or ()).upper() or "-"
        c.create_text(20, self.region["height"] - 20, anchor="w", fill=INK, font=("Consolas", 12, "bold"),
                      text=f"BOT  keys {keys}   {summary}" + ("" if p else "   (can't see you)"))
