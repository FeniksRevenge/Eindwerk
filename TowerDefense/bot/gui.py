"""
Swarm Bot app: a small window to calibrate, test and start/stop the screen bot.

Start it with start_app.bat (or: pyw gui.py). The * and - hotkeys keep working while
you're in Roblox; the buttons here do the same thing.
"""

import json
import os
import queue
import threading
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, ttk

from swarm_bot import (CONFIG_LOCK, CONFIG_PATH, FROZEN, SHOTS_DIR, BotController, apply_preset,
                       read_config_or_empty, save_config)
from phototrainer import list_photos, train_auto
from vision import CLASSES, DEFAULT_TOLERANCE

HERE = os.path.dirname(os.path.abspath(__file__))  # source folder (not used when frozen)

# Colors taken from the game: near-black playfield, its red, and the player's green-gray.
BG = "#07090d"
PANEL = "#11151c"
LINE = "#232a35"
FG = "#e4e7ec"
MUTED = "#8a93a1"
RED = "#e84a4a"
GREEN = "#6fdc8c"
AMBER = "#ffa040"
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI Semibold", 10)
MONO = ("Consolas", 9)

STATUS_COLORS = {
    "Idle": MUTED,
    "Running": GREEN,
    "Waiting for the player to appear...": AMBER,
    "Stopped": MUTED,
    "Stopped (died)": RED,
    "Error": RED,
}


def read_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_config(cfg):
    save_config(cfg)


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.proc = None  # running calibrate/view window, if any
        self.ctl = BotController(on_event=lambda kind, text: self.events.put((kind, text)))
        try:
            self.ctl.listen_hotkeys()
            hotkeys_ok = True
        except Exception as e:  # pynput missing or blocked
            hotkeys_ok = False
            self.events.put(("log", f"Hotkeys unavailable ({e}). Use the buttons."))

        root.title("Swarm Bot")
        root.configure(bg=BG)
        root.resizable(False, False)
        self._style()

        wrap = tk.Frame(root, bg=BG, padx=16, pady=14)
        wrap.pack(fill="both", expand=True)

        # --- status ------------------------------------------------------------
        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="SWARM BOT", bg=BG, fg=FG, font=("Consolas", 16, "bold")).pack(side="left")
        self.fps_var = tk.StringVar(value="")
        tk.Label(head, textvariable=self.fps_var, bg=BG, fg=MUTED, font=MONO).pack(side="right")

        status_box = tk.Frame(wrap, bg=PANEL, highlightbackground=LINE, highlightthickness=1, padx=12, pady=10)
        status_box.pack(fill="x", pady=(10, 10))
        self.dot = tk.Canvas(status_box, width=14, height=14, bg=PANEL, highlightthickness=0)
        self.dot.pack(side="left")
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill=MUTED, outline="")
        self.status_var = tk.StringVar(value="Idle")
        self.status_lbl = tk.Label(status_box, textvariable=self.status_var, bg=PANEL, fg=FG, font=("Segoe UI Semibold", 12))
        self.status_lbl.pack(side="left", padx=(8, 0))

        btns = tk.Frame(wrap, bg=BG)
        btns.pack(fill="x")
        self.start_btn = ttk.Button(btns, text="Start   ( * )", style="Go.TButton", command=self.start)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        ttk.Button(btns, text="Stop   ( - )", style="Stop.TButton", command=self.ctl.stop).pack(side="left", expand=True, fill="x")
        hint = ("Hotkeys work while you're in Roblox. It stops by itself when you die.\n"
                "Press / anytime to save a screenshot of what the bot sees.") if hotkeys_ok \
            else "Hotkeys are off; use the buttons."
        tk.Label(wrap, text=hint, bg=BG, fg=MUTED, font=FONT, justify="left").pack(anchor="w", pady=(6, 8))
        shots = tk.Frame(wrap, bg=BG)
        shots.pack(fill="x", pady=(0, 12))
        ttk.Button(shots, text="Screenshot  ( / )", command=self.ctl.screenshot).pack(side="left", padx=(0, 6))
        ttk.Button(shots, text="Open screenshots folder", command=self.open_shots).pack(side="left")

        # --- setup -------------------------------------------------------------
        self._section(wrap, "SETUP")
        setup = tk.Frame(wrap, bg=BG)
        setup.pack(fill="x")
        ttk.Button(setup, text="Use preset colors", command=self.use_preset).pack(side="left", padx=(0, 6))
        ttk.Button(setup, text="Set play area", command=lambda: self.launch("calibrate", "region")).pack(side="left", padx=(0, 6))
        ttk.Button(setup, text="Test view", command=lambda: self.launch("view")).pack(side="left")

        setup2 = tk.Frame(wrap, bg=BG)
        setup2.pack(fill="x", pady=(8, 0))
        ttk.Button(setup2, text="Calibrate everything", command=lambda: self.launch("calibrate")).pack(side="left", padx=(0, 6))
        ttk.Button(setup2, text="Calibrate from screenshot...", command=self.calibrate_from_file).pack(side="left")

        redo = tk.Frame(wrap, bg=BG)
        redo.pack(fill="x", pady=(8, 0))
        tk.Label(redo, text="Redo one:", bg=BG, fg=MUTED, font=FONT).pack(side="left")
        self.redo_var = tk.StringVar(value="boss")
        ttk.Combobox(redo, textvariable=self.redo_var, values=CLASSES, state="readonly", width=15).pack(side="left", padx=6)
        ttk.Button(redo, text="Calibrate", command=lambda: self.launch("calibrate", self.redo_var.get())).pack(side="left")

        self.calib_var = tk.StringVar()
        tk.Label(wrap, textvariable=self.calib_var, bg=BG, fg=MUTED, font=FONT, justify="left",
                 wraplength=380).pack(anchor="w", pady=(8, 12))

        # --- settings ----------------------------------------------------------
        self._section(wrap, "SETTINGS")
        cfg = read_config() or {}
        self.focus_var = tk.BooleanVar(value=cfg.get("require_focus", True))
        ttk.Checkbutton(wrap, text="Only control Roblox when it's the active window", variable=self.focus_var,
                        command=self.save_settings).pack(anchor="w")
        self.top_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(wrap, text="Keep this window on top", variable=self.top_var,
                        command=lambda: root.attributes("-topmost", self.top_var.get())).pack(anchor="w", pady=(2, 6))

        grid = tk.Frame(wrap, bg=BG)
        grid.pack(fill="x")
        tk.Label(grid, text="Auto screenshot every (s, 0 = off)", bg=BG, fg=FG, font=FONT).grid(
            row=3, column=0, sticky="w", pady=(6, 0))
        self.auto_var = tk.DoubleVar(value=cfg.get("auto_shot_every", 10))
        ttk.Spinbox(grid, from_=0, to=120, increment=5, textvariable=self.auto_var, width=6,
                    command=self.save_settings).grid(row=3, column=1, sticky="e", pady=(6, 0))
        tk.Label(grid, text="Shoot with", bg=BG, fg=FG, font=FONT).grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.fire_var = tk.StringVar(value="Space" if cfg.get("fire_with", "space") == "space" else "Left mouse")
        fire_box = ttk.Combobox(grid, textvariable=self.fire_var, values=["Space", "Left mouse"], state="readonly", width=12)
        fire_box.grid(row=2, column=1, sticky="e", pady=(6, 0))
        fire_box.bind("<<ComboboxSelected>>", lambda _e: self.save_settings())
        tk.Label(grid, text="Stop after player missing (s)", bg=BG, fg=FG, font=FONT).grid(row=0, column=0, sticky="w")
        self.death_var = tk.DoubleVar(value=cfg.get("death_timeout", 1.5))
        ttk.Spinbox(grid, from_=0.5, to=10, increment=0.5, textvariable=self.death_var, width=6,
                    command=self.save_settings).grid(row=0, column=1, sticky="e", padx=(12, 0))
        tk.Label(grid, text="Color tolerance", bg=BG, fg=FG, font=FONT).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tol = cfg.get("tolerance", DEFAULT_TOLERANCE)
        self.tol_var = tk.IntVar(value=int(tol[1]))
        ttk.Scale(grid, from_=6, to=30, variable=self.tol_var, length=150,
                  command=lambda _v: self.tol_lbl.config(text=str(self.tol_var.get()))).grid(row=1, column=1, pady=(6, 0))
        self.tol_lbl = tk.Label(grid, text=str(self.tol_var.get()), bg=BG, fg=MUTED, font=MONO, width=3)
        self.tol_lbl.grid(row=1, column=2, pady=(6, 0))
        grid.bind_all("<ButtonRelease-1>", lambda _e: self.save_settings(), add="+")
        grid.columnconfigure(0, weight=1)

        # --- photo trainer -----------------------------------------------------
        self._section(wrap, "PHOTO TRAINER", top=12)
        trow = tk.Frame(wrap, bg=BG)
        trow.pack(fill="x")
        ttk.Button(trow, text="Train on photos (ask me)", command=self.train_semi).pack(side="left", padx=(0, 6))
        ttk.Button(trow, text="Train on photos (auto)", command=self.train_auto).pack(side="left")
        self.photos_var = tk.StringVar()
        tk.Label(wrap, textvariable=self.photos_var, bg=BG, fg=MUTED, font=FONT, justify="left",
                 wraplength=400).pack(anchor="w", pady=(6, 0))
        self.training = False

        # --- log -------------------------------------------------------------
        self._section(wrap, "LOG", top=12)
        self.log = tk.Text(wrap, height=7, width=52, bg=PANEL, fg=FG, font=MONO, relief="flat",
                           highlightbackground=LINE, highlightthickness=1, state="disabled", padx=8, pady=6)
        self.log.pack(fill="x")

        self.refresh_calibration()
        self.refresh_photos()
        cfg_now = read_config() or {}
        if cfg_now.get("colors") and "preset" not in cfg_now:
            self.write_log("Your colors come from an older calibration that can mistake the background for a mob. "
                           "Click 'Use preset colors' to replace them.")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.poll)

    # ------------------------------------------------------------------ ui helpers
    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TButton", background=PANEL, foreground=FG, bordercolor=LINE, focuscolor=PANEL,
                    lightcolor=PANEL, darkcolor=PANEL, padding=(12, 6), font=FONT)
        s.map("TButton", background=[("active", LINE)])
        s.configure("Go.TButton", background="#173a24", foreground=GREEN, font=FONT_B, padding=(12, 10))
        s.map("Go.TButton", background=[("active", "#1f4d30")])
        s.configure("Stop.TButton", background="#3a1717", foreground=RED, font=FONT_B, padding=(12, 10))
        s.map("Stop.TButton", background=[("active", "#4d1f1f")])
        s.configure("TCheckbutton", background=BG, foreground=FG, font=FONT, focuscolor=BG)
        s.map("TCheckbutton", background=[("active", BG)])
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG, arrowcolor=FG, bordercolor=LINE)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", FG)])
        s.configure("TSpinbox", fieldbackground=PANEL, background=PANEL, foreground=FG, arrowcolor=FG, bordercolor=LINE)
        s.configure("Horizontal.TScale", background=BG, troughcolor=PANEL, bordercolor=LINE)
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)

    def _section(self, parent, title, top=0):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(top, 6))
        tk.Label(row, text=title, bg=BG, fg=MUTED, font=("Consolas", 9, "bold")).pack(side="left")
        tk.Frame(row, bg=LINE, height=1).pack(side="left", fill="x", expand=True, padx=(8, 0), pady=(2, 0))

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, text):
        self.status_var.set(text)
        self.dot.itemconfig(self.dot_id, fill=STATUS_COLORS.get(text, MUTED))
        if not text.startswith("Running") and not text.startswith("Waiting"):
            self.fps_var.set("")

    def refresh_calibration(self):
        cfg = read_config()
        if not cfg or "region" not in cfg:
            self.calib_var.set("Not set up yet. Click 'Use preset colors', then 'Set play area'.")
            self.start_btn.state(["disabled"])
            return
        done = [n for n in CLASSES if cfg.get("colors", {}).get(n)]
        missing = [n for n in CLASSES if n not in done]
        r = cfg["region"]
        text = f"Play area {r['width']}x{r['height']}.  Knows: {', '.join(done)}."
        if missing:
            text += f"\nNot set: {', '.join(missing)}."
        self.calib_var.set(text)
        self.start_btn.state(["!disabled"])

    # ------------------------------------------------------------------ actions
    def start(self):
        if self.proc and self.proc.poll() is None:
            self.write_log("Close the calibration/test window first.")
            return
        self.ctl.start()

    def launch(self, *args):
        if self.proc and self.proc.poll() is None:
            self.write_log("A calibration/test window is already open.")
            return
        self.ctl.stop()
        if FROZEN:  # SwarmBot.exe runs calibrate/view itself when given them as arguments
            cmd = [sys.executable, *args]
        else:
            cmd = [sys.executable, os.path.join(HERE, "swarm_bot.py"), *args]
        self.proc = subprocess.Popen(cmd, cwd=os.path.dirname(CONFIG_PATH))
        self.write_log(f"Opened {' '.join(args)} in a new window.")

    def refresh_photos(self):
        n = len(list_photos(SHOTS_DIR)) if os.path.isdir(SHOTS_DIR) else 0
        self.photos_var.set(f"{n} photo(s) waiting. Press / while playing to add more. "
                            "Each photo is deleted once it's been trained on." if n else
                            "No photos yet. Press / while playing to save some, then train on them here.")

    def train_semi(self):
        if not list_photos(SHOTS_DIR):
            self.write_log("No photos to train on yet. Press / while playing to save some.")
            return
        self.launch("train")

    def train_auto(self):
        if self.training or not list_photos(SHOTS_DIR):
            if not self.training:
                self.write_log("No photos to train on yet. Press / while playing to save some.")
            return
        self.training = True
        self.ctl.stop()
        self.write_log("Training on photos by itself...")

        def work():
            try:
                with CONFIG_LOCK:
                    cfg = read_config_or_empty()
                    msg = train_auto(cfg, SHOTS_DIR, lambda t: self.events.put(("progress", t)))
                    save_config(cfg)
            except Exception as e:
                msg = f"Photo training failed: {e}"
            self.events.put(("log", msg))
            self.events.put(("trained", ""))

        threading.Thread(target=work, daemon=True).start()

    def use_preset(self):
        has_region = apply_preset()
        self.write_log("Preset colors applied (measured from your screenshots)." +
                       ("" if has_region else " Now click 'Set play area'."))
        self.refresh_calibration()

    def calibrate_from_file(self):
        path = filedialog.askopenfilename(
            title="Pick a screenshot of the play area (not a _bot one)",
            initialdir=SHOTS_DIR if os.path.isdir(SHOTS_DIR) else os.path.dirname(CONFIG_PATH),
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if path:
            self.launch("calibrate", "--image", path)

    def open_shots(self):
        os.makedirs(SHOTS_DIR, exist_ok=True)
        if os.name == "nt":
            os.startfile(SHOTS_DIR)
        else:
            self.write_log(f"Screenshots are in {SHOTS_DIR}")

    def save_settings(self):
        with CONFIG_LOCK:
            self._save_settings()

    def _save_settings(self):
        cfg = read_config()
        if not cfg:
            return
        try:
            death = float(self.death_var.get())
            auto_every = max(0.0, float(self.auto_var.get()))
        except (tk.TclError, ValueError):
            return
        v = int(self.tol_var.get())
        new = {"require_focus": bool(self.focus_var.get()), "death_timeout": death,
               "fire_with": "space" if self.fire_var.get() == "Space" else "mouse",
               "auto_shot_every": auto_every,
               "tolerance": [round(v * 30 / 14), v, v]}
        if any(cfg.get(k) != val for k, val in new.items()):
            cfg.update(new)
            write_config(cfg)

    def poll(self):
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.set_status(text)
            elif kind == "fps":
                self.fps_var.set(f"{text} fps")
            elif kind == "progress":
                self.photos_var.set(text)
            elif kind == "trained":
                self.training = False
                self.refresh_photos()
                self.refresh_calibration()
            else:
                self.write_log(text)
                if text.startswith("Screenshot"):
                    self.refresh_photos()
        if self.proc and self.proc.poll() is not None:
            self.proc = None
            self.refresh_calibration()
            self.refresh_photos()
            self.write_log("Calibration/test window closed.")
        self.root.after(50, self.poll)

    def close(self):
        self.ctl.quit()
        self.root.destroy()


def selftest():
    """Used by the exe build: checks every bundled library loads and detection works."""
    import cv2
    import numpy as np
    import mss  # noqa: F401
    from pynput import keyboard  # noqa: F401
    from vision import Detector, measure_blob

    img = np.full((300, 400, 3), (11, 7, 5), np.uint8)
    cv2.circle(img, (100, 150), 22, (184, 178, 176), -1)
    cv2.circle(img, (300, 150), 14, (74, 74, 232), -1)
    cfg = {"colors": {}}
    for name, xy in (("player", (100, 150)), ("enemy_bullet", (300, 150))):
        lab, radius = measure_blob(img, *xy)
        cfg["colors"][name] = {"lab": lab, "radius": radius}
    found = Detector(cfg).detect(img)
    return len(found["player"]) == 1 and len(found["enemy_bullet"]) == 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--selftest":
        out = os.path.join(os.path.dirname(CONFIG_PATH), "selftest.txt")
        try:
            ok = selftest()
            msg = "ok" if ok else "detection failed"
        except Exception as e:
            ok, msg = False, f"error: {e!r}"
        with open(out, "w") as f:
            f.write(msg)
        sys.exit(0 if ok else 1)
    if args:  # calibrate / view, launched by the app itself
        from swarm_bot import main
        main(args)
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()
