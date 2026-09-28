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
import sys
import time

from mcp.server.mcpserver import Image, MCPServer
from PIL import ImageGrab

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

_last = {"ox": 0, "oy": 0, "scale": 1.0}      # where the last screenshot came from


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
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            t = _title(hwnd)
            x, y, w, h = _rect(hwnd)
            if t and w > 40 and h > 40:
                out.append((hwnd, t, (x, y, w, h)))
        return True

    user32.EnumWindows(cb, 0)
    return out


def _find(title: str):
    if not title:
        return None
    hits = [w for w in _windows() if title.lower() in w[1].lower()]
    if not hits:
        raise ValueError(f"no visible window with {title!r} in its title; try windows()")
    return hits[0]


@mcp.tool()
def windows() -> str:
    """List the visible top-level windows: title and screen rect (x, y, w, h)."""
    rows = [f"{t!r}  at x={x} y={y} w={w} h={h}" for _, t, (x, y, w, h) in _windows()]
    return "\n".join(rows) or "(no visible windows)"


@mcp.tool()
def focus(title: str) -> str:
    """Bring the window whose title contains `title` to the front."""
    hwnd, t, _ = _find(title)
    user32.ShowWindow(hwnd, 9)           # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)
    return f"focused {t!r}"


# ── eyes ─────────────────────────────────────────────────────────────────
@mcp.tool()
def screenshot(title: str = "", scale: float = 0.5, region: list[int] | None = None) -> list:
    """Capture a window (title substring), a screen `region` [x, y, w, h], or the whole
    desktop. `scale` shrinks the picture (0.5 = half size) to keep it cheap to read.
    Later mouse tools take coordinates in THIS picture."""
    if region:
        x, y, w, h = region
        what = f"region {region}"
    elif title:
        _, t, (x, y, w, h) = _find(title)
        what = f"window {t!r}"
    else:
        x = user32.GetSystemMetrics(76); y = user32.GetSystemMetrics(77)
        w = user32.GetSystemMetrics(78); h = user32.GetSystemMetrics(79)
        what = "the whole desktop"
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    if scale != 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    _last.update(ox=x, oy=y, scale=scale)
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
def click(x: float, y: float, button: str = "left", double: bool = False, space: str = "shot") -> str:
    """Click at a point. button: left | right | middle. Coordinates as in mouse_move."""
    sx, sy = _to_screen(x, y, space)
    down, up = _BUTTONS[button]
    _move_abs(sx, sy); time.sleep(0.05)
    for _ in range(2 if double else 1):
        _send(_mouse(down)); time.sleep(0.04); _send(_mouse(up)); time.sleep(0.06)
    return f"{'double ' if double else ''}{button} click at screen ({sx},{sy})"


@mcp.tool()
def drag(x1: float, y1: float, x2: float, y2: float, seconds: float = 0.4, space: str = "shot") -> str:
    """Press at (x1,y1), move to (x2,y2) over `seconds`, release."""
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
def key(combo: str, times: int = 1) -> str:
    """Press a key or chord: 'esc', 'enter', 'ctrl+c', 'alt+f4', 'shift+tab', 'f5', 'a'."""
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
def type_text(text: str, delay_ms: int = 12) -> str:
    """Type text into whatever has focus (any Unicode). Use key('enter') to submit."""
    for ch in text:
        if ch == "\n":
            key("enter"); continue
        for up in (False, True):
            i = INPUT(type=INPUT_KEYBOARD)
            i.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0), 0, None)
            _send(i)
        time.sleep(delay_ms / 1000)
    return f"typed {len(text)} chars"


@mcp.tool()
def wait(seconds: float = 1.0) -> str:
    """Let the app catch up (animations, loads) before the next screenshot."""
    time.sleep(min(30.0, max(0.0, seconds)))
    return f"waited {seconds}s"


if __name__ == "__main__":
    print("desktop MCP up", file=sys.stderr)
    mcp.run("stdio")
