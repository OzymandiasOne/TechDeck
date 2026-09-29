"""A local desktop-control MCP server: eyes and hands on THIS Windows desktop.

Dev-only (tools/devkit never ships). Claude Code starts it over stdio - no
port, no service, no admin. It gives the assistant the same access a person
at the keyboard has: a screenshot of a window, a real mouse click, real keys.
Everything is plain Win32 through ctypes plus Pillow for the capture, so it
runs under the locked-down IT setup (no installs beyond `pip install --user mcp`).

Register once (user scope, so it works from any project):
    claude mcp add -s user desktop -- python C:\\Dev\\TechDeck\\tools\\devkit\\desktop_mcp\\server.py

Coordinates: `screenshot` remembers where and how big it looked, so the mouse
tools take coordinates IN THAT PICTURE by default (space="shot"). Pass
space="screen" for raw screen pixels. Never print to stdout: that is the wire.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import io
import os
import shutil
import sys
import tempfile
import time

from mcp.server.mcpserver import Image, MCPServer
from PIL import Image as PILImage, ImageChops, ImageDraw, ImageGrab

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

# Physical pixels everywhere, or a 150% display makes every click land short.
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))     # PER_MONITOR_AWARE_V2
except Exception:
    user32.SetProcessDPIAware()

mcp = MCPServer(
    "desktop",
    instructions=(
        "Eyes and hands on the local Windows desktop. Loop: screenshot(title) -> look -> "
        "click/key/type -> screenshot. Mouse tools take coordinates in the LAST screenshot "
        "unless space='screen'. The person owns this desktop: act only on the window you "
        "were asked to test, and stop if something unexpected has focus."),
)

_last = {"ox": 0, "oy": 0, "scale": 1.0, "title": ""}   # where the last screenshot came from
_TMP = os.path.join(tempfile.gettempdir(), "desktop_mcp")   # burst frames live here, briefly
_driving = {"granted": False, "monitor": None}   # Accept pressed; the monitor it was pressed on (x, y, w, h)


# ── windows ──────────────────────────────────────────────────────────────
def _rect(hwnd) -> tuple[int, int, int, int]:
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:   # EXTENDED_FRAME_BOUNDS
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _windows() -> list[tuple[int, str, tuple[int, int, int, int]]]:
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            t = _title(hwnd)
            x, y, w, h = _rect(hwnd)
            if t and (w > 40 and h > 40 or user32.IsIconic(hwnd)):
                out.append((hwnd, t, (x, y, w, h)))
        return True

    user32.EnumWindows(cb, 0)
    return out


def _find(title: str):
    if not title:
        return None
    hits = [w for w in _windows() if title.lower() in w[1].lower()]
    if not hits:
        raise ValueError(f"no window with {title!r} in its title; call windows() to see what exists")
    exact = [w for w in hits if w[1].lower() == title.lower()]
    return (exact or hits)[0]


def _foreground_title() -> str:
    return _title(user32.GetForegroundWindow())


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def _monitor_at(x: int, y: int) -> tuple[int, int, int, int]:
    """The screen rect of the monitor under a point."""
    h = user32.MonitorFromPoint(wt.POINT(x, y), 2)          # MONITOR_DEFAULTTONEAREST
    mi = _MONITORINFO(); mi.cbSize = ctypes.sizeof(_MONITORINFO)
    user32.GetMonitorInfoW(h, ctypes.byref(mi))
    r = mi.rcMonitor
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _drive_monitor():
    return _driving["monitor"]


def _move_to_drive_monitor(hwnd):
    """Put a window on the test monitor (same size, centred) if it is elsewhere."""
    mon = _drive_monitor()
    if not mon:
        return
    mx, my, mw, mh = mon
    x, y, w, h = _rect(hwnd)
    if mx <= x + w // 2 < mx + mw and my <= y + h // 2 < my + mh:
        return
    user32.ShowWindow(hwnd, 9)
    w, h = min(w, mw), min(h, mh)
    user32.SetWindowPos(hwnd, None, mx + (mw - w) // 2, my + (mh - h) // 2, w, h, 0x0004 | 0x0040)   # NOZORDER|SHOWWINDOW


def _guard(force: bool):
    """Hands only move once the person pressed Accept on the pop-up, only touch
    the window that was last looked at, and only while it is in front. The
    person owns this desktop; a click into their Teams window is the one
    thing this tool must never do."""
    if not _driving["granted"]:
        raise ValueError("hands are locked: call request_drive() and wait for Accept")
    if force or not _last["title"]:
        return
    fg = _foreground_title()
    if _last["title"].lower() not in fg.lower():
        raise ValueError(f"refusing: the front window is {fg!r}, not {_last['title']!r}. "
                         f"focus() it first, or pass force=True if you mean it")


def _ask_to_drive(reason: str, timeout_s: int) -> bool:
    """A small top-most dialog with Accept / Decline. Runs in this process; the
    tool call blocks until the person answers or the timeout passes."""
    import tkinter as tk
    answer = {"ok": False}
    root = tk.Tk()
    root.title("Claude")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    root.configure(bg="#1b1b1f")
    tk.Label(root, text="Claude would like to drive.", font=("Segoe UI", 14, "bold"),
             fg="#f2f2f2", bg="#1b1b1f", padx=28, pady=(18)).pack()
    tk.Label(root, text=("When you're ready, select Accept or Decline.\n"
                         "Drag this box to the monitor Claude should use, then Accept.\n"
                         "Accept = hands off your mouse and keyboard until Claude says it is done."
                         + (f"\n\n{reason}" if reason else "")),
             font=("Segoe UI", 10), fg="#c8c8cc", bg="#1b1b1f", padx=28, pady=6, justify="left").pack()
    row = tk.Frame(root, bg="#1b1b1f"); row.pack(pady=(10, 18))

    def accept():
        answer["ok"] = True
        answer["at"] = (root.winfo_x() + root.winfo_width() // 2, root.winfo_y() + root.winfo_height() // 2)
        root.destroy()

    def decline():
        root.destroy()

    tk.Button(row, text="Accept", width=12, command=accept, bg="#2f9e44", fg="white",
              activebackground="#37b24d", relief="flat", font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
    tk.Button(row, text="Decline", width=12, command=decline, bg="#495057", fg="white",
              activebackground="#5c636a", relief="flat", font=("Segoe UI", 10)).pack(side="left", padx=8)
    root.after(int(timeout_s * 1000), root.destroy)
    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")
    root.bind("<Return>", lambda e: accept()); root.bind("<Escape>", lambda e: decline())
    root.focus_force()
    root.mainloop()
    if answer["ok"]:
        _driving["monitor"] = _monitor_at(*answer["at"])
    return answer["ok"]


@mcp.tool()
def request_drive(reason: str = "", timeout_s: int = 120) -> str:
    """Ask the person for the mouse and keyboard. Shows a top-most pop-up
    ('Claude would like to drive... Accept / Decline') and waits. Hands stay
    locked until this returns 'accepted'. Call it once per run; release_drive()
    when done so they get their desk back."""
    ok = _ask_to_drive(reason, timeout_s)
    _driving["granted"] = ok
    return (f"accepted: you may drive now (they were asked to keep hands off). Test monitor: "
            f"{_driving['monitor']} - focus() moves the window there; screenshot() with no title shows it") if ok else \
        "declined or timed out: hands stay locked; ask in chat when they are ready"


@mcp.tool()
def release_drive() -> str:
    """Give the desk back: locks the hands again. Say so in chat too."""
    _driving["granted"] = False
    return "released: hands locked until the next request_drive()"


@mcp.tool()
def windows() -> str:
    """List the visible top-level windows: title and screen rect (x, y, w, h)."""
    rows = [f"{t!r}  at x={x} y={y} w={w} h={h}" + ("  (minimized)" if user32.IsIconic(h_) else "")
            for h_, t, (x, y, w, h) in _windows()]
    return "\n".join(rows) or "(no visible windows)"


@mcp.tool()
def focus(title: str) -> str:
    """Bring the window whose title contains `title` to the front."""
    hwnd, t, _ = _find(title)
    user32.ShowWindow(hwnd, 9)           # SW_RESTORE
    _move_to_drive_monitor(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)
    return f"focused {t!r} at {_rect(hwnd)}"


# ── eyes ─────────────────────────────────────────────────────────────────
@mcp.tool()
def screenshot(title: str = "", scale: float = 0.5, region: list[int] | None = None) -> list:
    """Capture a window (title substring), a screen `region` [x, y, w, h], or the whole
    desktop. `scale` shrinks the picture (0.5 = half size) to keep it cheap to read.
    Later mouse tools take coordinates in THIS picture."""
    t = ""
    if region:
        x, y, w, h = region
        what = f"region {region}"
    elif title:
        try:
            _, t, (x, y, w, h) = _find(title)
        except ValueError as why:
            return [str(why)]
        what = f"window {t!r}"
    elif _drive_monitor():
        x, y, w, h = _drive_monitor()
        what = "the test monitor"
    else:
        x = user32.GetSystemMetrics(76); y = user32.GetSystemMetrics(77)
        w = user32.GetSystemMetrics(78); h = user32.GetSystemMetrics(79)
        what = "the whole desktop"
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    if scale != 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    _last.update(ox=x, oy=y, scale=scale, title=t)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    note = (f"{what}: screen origin ({x},{y}) size {w}x{h}, shown at scale {scale} "
            f"({img.width}x{img.height}). Mouse coordinates in this picture are accepted as-is.")
    return [note, Image(data=buf.getvalue(), format="png")]


# ── hands ────────────────────────────────────────────────────────────────
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x0001, 0x8000, 0x4000
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def _send(*inputs: INPUT):
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError(f"SendInput sent {sent} of {len(inputs)}")


def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    i = INPUT(type=INPUT_MOUSE)
    i.mi = MOUSEINPUT(dx, dy, data, flags, 0, None)
    return i


def _to_screen(x: float, y: float, space: str) -> tuple[int, int]:
    if space == "screen":
        return int(x), int(y)
    return int(_last["ox"] + x / _last["scale"]), int(_last["oy"] + y / _last["scale"])


def _move_abs(sx: int, sy: int):
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    nx = int((sx - vx) * 65535 / max(1, vw - 1)); ny = int((sy - vy) * 65535 / max(1, vh - 1))
    _send(_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny))


_BUTTONS = {"left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
            "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
            "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP)}


@mcp.tool()
def mouse_move(x: float, y: float, space: str = "shot") -> str:
    """Move the mouse (hover). Coordinates in the last screenshot, or space='screen'."""
    sx, sy = _to_screen(x, y, space)
    _move_abs(sx, sy)
    return f"mouse at screen ({sx},{sy})"


@mcp.tool()
def click(x: float, y: float, button: str = "left", double: bool = False, space: str = "shot",
          force: bool = False) -> str:
    """Click at a point. button: left | right | middle. Coordinates as in mouse_move.
    Refused unless the last screenshot's window is in front (force=True overrides)."""
    _guard(force)
    sx, sy = _to_screen(x, y, space)
    down, up = _BUTTONS[button]
    _move_abs(sx, sy); time.sleep(0.05)
    for _ in range(2 if double else 1):
        _send(_mouse(down)); time.sleep(0.04); _send(_mouse(up)); time.sleep(0.06)
    return f"{'double ' if double else ''}{button} click at screen ({sx},{sy})"


@mcp.tool()
def drag(x1: float, y1: float, x2: float, y2: float, seconds: float = 0.4, space: str = "shot",
         force: bool = False) -> str:
    """Press at (x1,y1), move to (x2,y2) over `seconds`, release."""
    _guard(force)
    a, b = _to_screen(x1, y1, space), _to_screen(x2, y2, space)
    _move_abs(*a); time.sleep(0.05); _send(_mouse(MOUSEEVENTF_LEFTDOWN))
    steps = max(4, int(seconds * 60))
    for i in range(1, steps + 1):
        k = i / steps
        _move_abs(int(a[0] + (b[0] - a[0]) * k), int(a[1] + (b[1] - a[1]) * k))
        time.sleep(seconds / steps)
    _send(_mouse(MOUSEEVENTF_LEFTUP))
    return f"dragged {a} -> {b}"


@mcp.tool()
def scroll(x: float, y: float, clicks: int = -3, space: str = "shot") -> str:
    """Wheel-scroll at a point. Negative clicks scroll down."""
    sx, sy = _to_screen(x, y, space)
    _move_abs(sx, sy); time.sleep(0.05)
    _send(_mouse(MOUSEEVENTF_WHEEL, data=int(clicks * 120) & 0xFFFFFFFF))
    return f"scrolled {clicks} at ({sx},{sy})"


_VK = {"esc": 0x1B, "escape": 0x1B, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "space": 0x20,
       "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21,
       "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "insert": 0x2D,
       "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "capslock": 0x14,
       **{f"f{i}": 0x6F + i for i in range(1, 13)}}


def _vk(name: str) -> int:
    n = name.lower()
    if n in _VK:
        return _VK[n]
    if len(n) == 1:
        code = user32.VkKeyScanW(ord(n)) & 0xFF
        if code != 0xFF:
            return code
    raise ValueError(f"unknown key {name!r}")


def _key(vk: int, up: bool = False) -> INPUT:
    i = INPUT(type=INPUT_KEYBOARD)
    i.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
    return i


@mcp.tool()
def key(combo: str, times: int = 1, force: bool = False) -> str:
    """Press a key or chord: 'esc', 'enter', 'ctrl+c', 'alt+f4', 'shift+tab', 'f5', 'a'."""
    _guard(force)
    names = [p for p in combo.replace(" ", "").split("+") if p]
    vks = [_vk(n) for n in names]
    for _ in range(times):
        for vk in vks:
            _send(_key(vk)); time.sleep(0.02)
        for vk in reversed(vks):
            _send(_key(vk, up=True)); time.sleep(0.02)
        time.sleep(0.05)
    return f"pressed {combo} x{times}"


@mcp.tool()
def type_text(text: str, delay_ms: int = 12, force: bool = False) -> str:
    """Type text into whatever has focus (any Unicode). Use key('enter') to submit."""
    _guard(force)
    for ch in text:
        if ch == "\n":
            key("enter", force=True); continue
        for up in (False, True):
            i = INPUT(type=INPUT_KEYBOARD)
            i.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0), 0, None)
            _send(i)
        time.sleep(delay_ms / 1000)
    return f"typed {len(text)} chars"


@mcp.tool()
def record(title: str = "", seconds: float = 4.0, fps: float = 3.0, scale: float = 0.35,
           columns: int = 4, only_changes: bool = True) -> list:
    """Watch a window for a while: grab frames at `fps` for `seconds`, return them
    as ONE contact sheet (left-to-right, top-to-bottom, each frame stamped with
    its time). With only_changes, frames identical to the previous one are
    dropped, so a quiet screen costs one frame. Frames are deleted afterwards;
    nothing is kept on disk. Use it for anything that moves: dialogue, animation."""
    if title:
        try:
            _, t, (x, y, w, h) = _find(title)
        except ValueError as why:
            return [str(why)]
    elif _drive_monitor():
        t = ""
        x, y, w, h = _drive_monitor()
    else:
        t = ""
        x, y = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        w, h = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    shutil.rmtree(_TMP, ignore_errors=True); os.makedirs(_TMP, exist_ok=True)
    frames, stamps, prev = [], [], None
    n = max(1, int(seconds * fps)); period = 1.0 / max(0.2, fps); t0 = time.perf_counter()
    for i in range(n):
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        small = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        if not only_changes or prev is None or ImageChops.difference(small, prev).getbbox():
            path = os.path.join(_TMP, f"f{i:03d}.png"); small.save(path)
            frames.append(path); stamps.append(time.perf_counter() - t0)
        prev = small
        time.sleep(max(0.0, t0 + (i + 1) * period - time.perf_counter()))
    fw, fh = prev.size
    cols = max(1, min(columns, len(frames))); rows = (len(frames) + cols - 1) // cols
    sheet = PILImage.new("RGB", (cols * fw, rows * fh), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    for k, (path, ts) in enumerate(zip(frames, stamps)):
        fr = PILImage.open(path)
        px, py = (k % cols) * fw, (k // cols) * fh
        sheet.paste(fr, (px, py))
        draw.rectangle([px, py, px + 46, py + 13], fill=(0, 0, 0))
        draw.text((px + 3, py + 1), f"{ts:4.1f}s", fill=(255, 220, 90))
    shutil.rmtree(_TMP, ignore_errors=True)
    buf = io.BytesIO(); sheet.save(buf, format="PNG")
    note = (f"{len(frames)} frame(s) of {n} over {seconds}s at {fps} fps"
            f"{' (unchanged frames dropped)' if only_changes else ''}; "
            f"{(repr(t) if t else 'desktop')} at scale {scale}, {cols} per row. Mouse coordinates are NOT in this picture: "
            f"take a screenshot() before clicking.")
    return [note, Image(data=buf.getvalue(), format="png")]


@mcp.tool()
def wait(seconds: float = 1.0) -> str:
    """Let the app catch up (animations, loads) before the next screenshot."""
    time.sleep(min(30.0, max(0.0, seconds)))
    return f"waited {seconds}s"


if __name__ == "__main__":
    print("desktop MCP up", file=sys.stderr)
    mcp.run("stdio")
