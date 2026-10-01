"""
Swarm Bot: plays the Roblox swarm game in its window.

    *   start          -   stop          /   save a screenshot of what it sees
    +   save the last 8 seconds (pictures + what it saw and did), to send when something goes wrong
"""

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import winio  # noqa: F401  (first: real screen pixels with Windows display scaling)

FROZEN = getattr(sys, "frozen", False)
HOME = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
CONFIG = os.path.join(HOME, "config.json")
PICTURES = os.path.join(HOME, "pictures")

BG, PANEL, LINE, FG, MUTED = "#07090d", "#11151c", "#232a35", "#e4e7ec", "#8a93a1"
GREEN, RED, AMBER = "#6fdc8c", "#e84a4a", "#ffa040"
FONT, MONO = ("Segoe UI", 10), ("Consolas", 9)


def load_settings():
    try:
        with open(CONFIG) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {"auto_restart": bool(s.get("auto_restart", True)), "require_focus": bool(s.get("require_focus", True))}


def save_settings(s):
    try:
        with open(CONFIG, "w") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


class Bot:
    """Runs the bot loop on its own thread; talks to the window through on_event(kind, text)."""

    def __init__(self, on_event):
        self.on_event = on_event
        self.settings = load_settings()
        self._start, self._stop, self._quit = threading.Event(), threading.Event(), threading.Event()
        self._snap, self._rec = threading.Event(), threading.Event()
        self.running = False
        self.runner = None
        threading.Thread(target=self._loop, daemon=True).start()

    def start(self):
        self._start.set()

    def stop(self):
        self._stop.set()

    def snapshot(self):
        self._snap.set()

    def save_recording(self):
        self._rec.set()

    def quit(self):
        self._quit.set()
        self._stop.set()

    def hotkeys(self):
        from pynput import keyboard

        def on_press(k):
            ch, vk = getattr(k, "char", None), getattr(k, "vk", None)
            if ch == "*" or vk == 106:
                self.start()
            elif ch == "-" or vk in (109, 189):
                self.stop()
            elif ch == "/" or vk == 111:
                self.snapshot()
            elif ch == "+" or vk == 107:
                self.save_recording()
        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

    def _loop(self):
        from runner import BotRunner
        from winio import WindowsIO
        io, last_status, frames, fps_t = None, None, 0, time.perf_counter()
        while not self._quit.is_set():
            if self._snap.is_set():
                self._snap.clear()
                self._save_picture()
            if self._rec.is_set():
                self._rec.clear()
                self._save_recording()
            if self._start.is_set():
                self._start.clear()
                self._stop.clear()
                if not self.running:
                    io = WindowsIO(self.settings["require_focus"])
                    self.runner = BotRunner(io, self.settings["auto_restart"], log=lambda t: self.on_event("log", t))
                    self.running = True
                    last_status = None
                    self.on_event("log", "Started.")
            if self._stop.is_set():
                self._stop.clear()
                if self.running:
                    self.running = False
                    io.close()
                    self.on_event("status", "Stopped")
                    self.on_event("log", "Stopped.")
            if not self.running:
                time.sleep(0.03)
                continue
            self.runner.auto_restart = self.settings["auto_restart"]
            try:
                status = self.runner.step()
            except Exception as e:
                self.running = False
                io.close()
                self.on_event("status", "Error")
                self.on_event("log", f"Error, stopped: {e!r}")
                continue
            if status == "dead":
                self.running = False
                io.close()
                self.on_event("status", "Stopped (game over)")
                self.on_event("log", f"Game over after {self.runner.run_seconds():.0f} s. Stopped. Press * to start again.")
                continue
            shown = {"playing": "Playing", "waiting": "Waiting for you to appear...", "restarting": "Restarting...",
                     "no_window": "Roblox window not found"}[status]
            if shown != last_status:
                self.on_event("status", shown)
                last_status = shown
            frames += 1
            if time.perf_counter() - fps_t > 1:
                r = self.runner
                self.on_event("fps", f"{frames / (time.perf_counter() - fps_t):.0f} fps, delay "
                                     f"{1000 * (r.latency + r.input_delay):.0f} ms" +
                              (f", speed {r.player_speed:.0f}" if r.player_speed else ""))
                frames, fps_t = 0, time.perf_counter()
        if io is not None:
            io.close()

    # ------------------------------------------------------------------ pictures
    def _save_picture(self):
        import cv2
        r = self.runner
        frame, pic = (r.picture() if r else (None, None))
        if frame is None:
            from winio import find_roblox
            import mss
            import numpy as np
            _, area = find_roblox()
            if area is None:
                self.on_event("log", "Screenshot: Roblox window not found.")
                return
            with mss.mss() as sct:
                frame = np.ascontiguousarray(np.asarray(sct.grab(area))[:, :, :3])
            from vision import Detector, annotate
            p, th = Detector().detect(frame)
            pic = annotate(frame, p, th, text="(bot not running)")
        os.makedirs(PICTURES, exist_ok=True)
        base = os.path.join(PICTURES, "shot_" + time.strftime("%Y%m%d_%H%M%S"))
        cv2.imwrite(base + ".png", frame)
        cv2.imwrite(base + "_bot.png", pic)
        self.on_event("log", f"Screenshot saved: {os.path.basename(base)}.png (+ _bot.png)")

    def _save_recording(self):
        import cv2
        import numpy as np
        from vision import DRAW
        r = self.runner
        if r is None or not r.recording:
            self.on_event("log", "Nothing recorded yet (it records while running).")
            return
        items = list(r.recording)
        folder = os.path.join(PICTURES, "rec_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(folder, exist_ok=True)
        log = []
        for i, (t, jpg, info) in enumerate(items):
            img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            for kind, x, y, rad in info["things"]:
                cv2.circle(img, (x // 2, y // 2), rad // 2 + 2, DRAW.get(kind, (255, 255, 255)), 1)
            if info["player"]:
                x, y, rad = info["player"]
                cv2.circle(img, (int(x) // 2, int(y) // 2), int(rad) // 2, (255, 255, 255), 2)
            cv2.putText(img, f"{t - items[0][0]:5.2f}s keys {''.join(k[0].upper() for k in info['keys']) or '-'} "
                             f"{info['note']}", (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 255, 140), 1)
            cv2.imwrite(os.path.join(folder, f"{i:04d}.jpg"), img)
            log.append(info)
        with open(os.path.join(folder, "log.json"), "w") as f:
            json.dump(log, f)
        self.on_event("log", f"Saved the last {items[-1][0] - items[0][0]:.0f} s: pictures/{os.path.basename(folder)} "
                             "(zip that folder and send it).")


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.bot = Bot(lambda kind, text: self.events.put((kind, text)))
        try:
            self.bot.hotkeys()
            hot = "Keys work while you're in Roblox:  *  start    -  stop    /  screenshot    +  save last 8 s"
        except Exception as e:
            hot = f"Hotkeys unavailable ({e}); use the buttons."
        root.title("Swarm Bot")
        root.configure(bg=BG)
        root.resizable(False, False)
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", background=PANEL, foreground=FG, bordercolor=LINE, padding=(10, 6), font=FONT)
        style.map("TButton", background=[("active", "#1a2030")])
        style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT)
        style.map("TCheckbutton", background=[("active", BG)])
        wrap = tk.Frame(root, bg=BG, padx=16, pady=14)
        wrap.pack(fill="both", expand=True)

        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="SWARM BOT", bg=BG, fg=FG, font=("Consolas", 16, "bold")).pack(side="left")
        self.fps = tk.StringVar()
        tk.Label(head, textvariable=self.fps, bg=BG, fg=MUTED, font=MONO).pack(side="right")
        box = tk.Frame(wrap, bg=PANEL, highlightbackground=LINE, highlightthickness=1, padx=12, pady=10)
        box.pack(fill="x", pady=(10, 10))
        self.dot = tk.Canvas(box, width=14, height=14, bg=PANEL, highlightthickness=0)
        self.dot.pack(side="left")
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill=MUTED, outline="")
        self.status = tk.StringVar(value="Idle")
        tk.Label(box, textvariable=self.status, bg=PANEL, fg=FG, font=("Segoe UI Semibold", 12)).pack(side="left", padx=8)

        row = tk.Frame(wrap, bg=BG)
        row.pack(fill="x")
        ttk.Button(row, text="Start  ( * )", command=self.bot.start).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ttk.Button(row, text="Stop  ( - )", command=self.bot.stop).pack(side="left", expand=True, fill="x")
        tk.Label(wrap, text=hot, bg=BG, fg=MUTED, font=FONT).pack(anchor="w", pady=(6, 8))

        s = self.bot.settings
        self.auto = tk.BooleanVar(value=s["auto_restart"])
        self.focus = tk.BooleanVar(value=s["require_focus"])
        ttk.Checkbutton(wrap, text="Auto restart: click PLAY AGAIN after a game over", variable=self.auto,
                        command=self.save).pack(anchor="w")
        ttk.Checkbutton(wrap, text="Only press keys while Roblox is the window in front", variable=self.focus,
                        command=self.save).pack(anchor="w", pady=(2, 8))

        row2 = tk.Frame(wrap, bg=BG)
        row2.pack(fill="x")
        ttk.Button(row2, text="Screenshot  ( / )", command=self.bot.snapshot).pack(side="left", padx=(0, 6))
        ttk.Button(row2, text="Save last 8 s  ( + )", command=self.bot.save_recording).pack(side="left", padx=(0, 6))
        ttk.Button(row2, text="Open folder", command=self.open_folder).pack(side="left")

        self.log = tk.Text(wrap, height=10, width=74, bg=PANEL, fg=FG, font=MONO, relief="flat",
                           highlightbackground=LINE, highlightthickness=1, wrap="word")
        self.log.pack(fill="both", pady=(10, 0))
        self.write("Open the game in Roblox, start a run, then press * (or Start).")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.poll)

    def save(self):
        self.bot.settings.update(auto_restart=bool(self.auto.get()), require_focus=bool(self.focus.get()))
        save_settings(self.bot.settings)

    def open_folder(self):
        os.makedirs(PICTURES, exist_ok=True)
        if os.name == "nt":
            os.startfile(PICTURES)
        else:
            self.write(PICTURES)

    def write(self, text):
        self.log.insert("end", time.strftime("%H:%M:%S  ") + text + "\n")
        self.log.see("end")

    def poll(self):
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.status.set(text)
                color = GREEN if text == "Playing" else AMBER if text.startswith(("Waiting", "Restarting", "Roblox")) \
                    else RED if text.startswith(("Stopped (", "Error")) else MUTED
                self.dot.itemconfig(self.dot_id, fill=color)
                if text != "Playing":
                    self.fps.set("")
            elif kind == "fps":
                self.fps.set(text)
            else:
                self.write(text)
        self.root.after(50, self.poll)

    def close(self):
        self.bot.quit()
        self.root.after(150, self.root.destroy)


def selftest():
    """For the exe build: every part loads, and it sees and decides on a drawn test picture."""
    import cv2
    import numpy as np
    import mss  # noqa: F401
    from pynput import keyboard  # noqa: F401
    from planner import Planner
    from tracker import Tracker
    from vision import COLORS, Detector

    def bgr(lab):
        return tuple(int(v) for v in cv2.cvtColor(np.uint8([[lab]]), cv2.COLOR_LAB2BGR)[0, 0])
    img = np.full((1116, 1984, 3), (8, 5, 4), np.uint8)
    cv2.ellipse(img, (1010, 560), (19, 37), 20, 0, 360, bgr(COLORS["white"][0]), -1)
    cv2.circle(img, (990, 555), 19, bgr(COLORS["gray"][0]), -1)
    cv2.circle(img, (1300, 560), 11, bgr(COLORS["red"][0]), -1)
    cv2.rectangle(img, (500, 300), (557, 357), bgr(COLORS["red"][1]), -1)
    player, things = Detector().detect(img)
    kinds = sorted(t.kind for t in things)
    if player is None or kinds != ["bullet", "grunt"]:
        return False
    tracks = Tracker().update(things, 1 / 30, player[:2], 1000, 600)
    keys, aim = Planner().plan(player, 558, tracks, 1984, 1116)
    return aim is not None


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        out = os.path.join(HOME, "selftest.txt")
        try:
            ok = selftest()
            msg = "ok" if ok else "detection/planning failed"
        except Exception as e:
            ok, msg = False, f"error: {e!r}"
        with open(out, "w") as f:
            f.write(msg)
        sys.exit(0 if ok else 1)
    root = tk.Tk()
    App(root)
    root.mainloop()
