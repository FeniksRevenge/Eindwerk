"""
"What the bot knows": a window listing every kind of thing the bot recognizes (the player and its
looks, bullets, mobs, health) with its color, size, how it was learned and its danger size, plus the
"not a thing" ignore list. From here you can relearn a thing, reset it to the preset, or remove a
learned player look / ignore entry.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

from swarm_bot import CONFIG_LOCK, CONFIG_PATH, PRESET, SHOTS_DIR, read_config_or_empty, save_config
from vision import CLASS_HELP, CLASSES, PLAYER_WHITE, set_main_player

BG = "#07090d"
PANEL = "#11151c"
LINE = "#232a35"
FG = "#e4e7ec"
MUTED = "#8a93a1"
FONT = ("Segoe UI", 10)


def lab_to_hex(lab):
    b, g, r = cv2.cvtColor(np.uint8([[[int(v) for v in lab]]]), cv2.COLOR_LAB2BGR)[0, 0]
    return f"#{r:02x}{g:02x}{b:02x}"


class KnowledgeWindow:
    def __init__(self, master, launch, log):
        """launch(*args): opens a calibration window (the app's own launcher). log(text): app log."""
        self.launch, self.log = launch, log
        self.win = tk.Toplevel(master)
        self.win.title("Swarm Bot - what it knows")
        self.win.configure(bg=BG)
        self.win.geometry("1060x560")
        tk.Label(self.win, text="Everything the bot recognizes. Select a row, then use the buttons below.",
                 bg=BG, fg=FG, font=FONT, anchor="w").pack(fill="x", padx=12, pady=(10, 4))

        frame = tk.Frame(self.win, bg=BG)
        frame.pack(fill="both", expand=True, padx=12)
        style = ttk.Style(self.win)
        style.configure("Know.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=22,
                        borderwidth=0)
        style.configure("Know.Treeview.Heading", background=LINE, foreground=FG, relief="flat")
        style.map("Know.Treeview", background=[("selected", "#2b3a55")], foreground=[("selected", "#ffffff")])
        cols = ("what", "lab", "size", "learned", "danger")
        self.tree = ttk.Treeview(frame, columns=cols, selectmode="browse", style="Know.Treeview")
        for col, text, width in (("#0", "Thing", 200), ("what", "What it is", 280), ("lab", "Color (L a b)", 110),
                                 ("size", "Size", 70), ("learned", "Learned from", 130), ("danger", "Danger size", 80)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, anchor="w", stretch=col == "what")
        bar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        btns = tk.Frame(self.win, bg=BG)
        btns.pack(fill="x", padx=12, pady=(8, 2))
        ttk.Button(btns, text="Relearn selected (screenshot now)", command=self.relearn).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Relearn from screenshots...", command=self.relearn_from_files).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Reset selected to preset", command=self.reset).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Make main look", command=self.make_main).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Remove selected", command=self.remove).pack(side="left")
        tk.Label(self.win, text=("Relearn the player when its look changes: click on yourself in the screenshot. "
                                 "Its old look is kept, so both keep working.\n"
                                 "Danger size is set in the main window. Changes are used the next time you press *."),
                 bg=BG, fg=MUTED, font=FONT, justify="left", anchor="w").pack(fill="x", padx=12, pady=(4, 10))

        self.swatches = []
        self.mtime = None
        self.refresh()
        self.win.after(1500, self.poll)

    # ------------------------------------------------------------------ list
    def _swatch(self, lab):
        img = tk.PhotoImage(width=18, height=12)
        img.put(lab_to_hex(lab), to=(0, 0, 18, 12))
        self.swatches.append(img)
        return img

    def poll(self):
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            m = os.path.getmtime(CONFIG_PATH)
        except OSError:
            m = None
        if m != self.mtime:  # a calibration window (or the trainer) changed what it knows
            self.refresh()
        self.win.after(1500, self.poll)

    def refresh(self):
        try:
            self.mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            self.mtime = None
        cfg = read_config_or_empty()
        keep = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.swatches = []
        colors = cfg.get("colors", {})
        expand = cfg.get("expand", {})
        for name in CLASSES:
            c = colors.get(name)
            if not (c and c.get("lab")):
                self.tree.insert("", "end", iid=f"cls:{name}", text=f"  {name}",
                                 values=(CLASS_HELP[name], "-", "-", "NOT SET (won't be seen)", "-"))
                continue
            learned = (f"{c['n']} example(s)" if c.get("n") else "preset colors" if cfg.get("preset") else "calibration")
            danger = "-" if name in ("player", "health") else f"{float(expand.get(name, 1.0)):g}x"
            self.tree.insert("", "end", iid=f"cls:{name}", text=f"  {name}", image=self._swatch(c["lab"]), open=True,
                             values=(CLASS_HELP[name], " ".join(str(int(v)) for v in c["lab"]),
                                     f"{float(c['radius']):.0f} px", learned, danger))
            if name == "player":
                self.tree.insert("cls:player", "end", iid="look:white", text="  look: white UFO",
                                 image=self._swatch(PLAYER_WHITE),
                                 values=("built in (also behind the HUD panels)", " ".join(map(str, PLAYER_WHITE)),
                                         "any", "built in", "-"))
                for i, look in enumerate(cfg.get("player_looks", [])):
                    self.tree.insert("cls:player", "end", iid=f"look:{i}", text=f"  look {i + 1}",
                                     image=self._swatch(look["lab"]),
                                     values=("an older look you taught it (still recognized)",
                                             " ".join(str(int(v)) for v in look["lab"]), f"{float(look['radius']):.0f} px",
                                             f"{look['n']} example(s)" if look.get("n") else "relearn / trainer", "-"))
        ignore = cfg.get("ignore", [])
        self.tree.insert("", "end", iid="ignore", text=f"  Not a thing ({len(ignore)})", open=True,
                         values=("ignore list: things you said aren't anything (photo trainer)", "", "", "", ""))
        for i, ig in enumerate(ignore):
            self.tree.insert("ignore", "end", iid=f"ign:{i}", text=f"  ignored {i + 1}", image=self._swatch(ig["lab"]),
                             values=("ignored (never the player)", " ".join(str(int(v)) for v in ig["lab"]),
                                     f"{float(ig['radius']):.0f} px", "photo trainer", "-"))
        for iid in keep:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.see(iid)

    def _selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _class_of(self, iid):
        if iid and iid.startswith("cls:"):
            return iid[4:]
        if iid and iid.startswith("look:"):
            return "player"
        return None

    # ------------------------------------------------------------------ actions
    def relearn(self):
        name = self._class_of(self._selected())
        if not name:
            messagebox.showinfo("Relearn", "Select a thing first (e.g. player).", parent=self.win)
            return
        self.launch("calibrate", name)
        self.log(f"Relearning {name}: press Enter in the calibration window, switch to Roblox, "
                 f"then click on {CLASS_HELP[name]}.")

    def relearn_from_files(self):
        name = self._class_of(self._selected())
        if not name:
            messagebox.showinfo("Relearn", "Select a thing first (e.g. player).", parent=self.win)
            return
        paths = filedialog.askopenfilenames(
            parent=self.win, title=f"Screenshots with {name} on them (Ctrl/Shift-click for several)",
            initialdir=SHOTS_DIR if os.path.isdir(SHOTS_DIR) else os.path.dirname(CONFIG_PATH),
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        paths = [p for p in paths if not p.endswith("_bot.png")]
        if paths:
            self.launch("calibrate", "--images", *paths, name)
            self.log(f"Relearning {name} from {len(paths)} screenshot(s): click it on each, N = next, Esc = done.")

    def reset(self):
        iid = self._selected()
        name = self._class_of(iid)
        if not name or iid.startswith("look:"):
            messagebox.showinfo("Reset", "Select a thing (a top row), e.g. grunt.", parent=self.win)
            return
        with CONFIG_LOCK:
            cfg = read_config_or_empty()
            r = cfg.get("region")
            scale = r["height"] / PRESET["ref_height"] if r else 1.0
            p = PRESET["colors"][name]
            look = {"lab": list(p["lab"]), "radius": round(p["radius"] * scale, 1)}
            if name == "player":
                set_main_player(cfg, look["lab"], look["radius"])
            else:
                cfg.setdefault("colors", {})[name] = look
            save_config(cfg)
        self.log(f"{name} reset to the preset color and size.")
        self.refresh()

    def make_main(self):
        iid = self._selected()
        if not (iid and iid.startswith("look:") and iid != "look:white"):
            messagebox.showinfo("Main look", "Select one of the player's learned looks.", parent=self.win)
            return
        with CONFIG_LOCK:
            cfg = read_config_or_empty()
            look = cfg.get("player_looks", [])[int(iid[5:])]
            set_main_player(cfg, look["lab"], look["radius"])
            save_config(cfg)
        self.log("Player: main look changed (the old one is kept as an extra look).")
        self.refresh()

    def remove(self):
        iid = self._selected()
        if not iid:
            return
        with CONFIG_LOCK:
            cfg = read_config_or_empty()
            if iid.startswith("look:") and iid != "look:white":
                cfg.get("player_looks", []).pop(int(iid[5:]))
                what = "player look"
            elif iid.startswith("ign:"):
                cfg.get("ignore", []).pop(int(iid[4:]))
                what = "ignore entry"
            elif iid.startswith("cls:") and iid != "cls:player":
                if not messagebox.askyesno("Remove", f"Forget {iid[4:]}? The bot won't see it anymore until you "
                                                     "relearn or reset it.", parent=self.win):
                    return
                cfg.get("colors", {}).pop(iid[4:], None)
                what = iid[4:]
            else:
                messagebox.showinfo("Remove", "The player and its built-in white look can't be removed; "
                                              "relearn the player instead.", parent=self.win)
                return
            save_config(cfg)
        self.log(f"Removed {what}.")
        self.refresh()
