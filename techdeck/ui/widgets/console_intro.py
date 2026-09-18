"""The startup invitation types itself out while the rest of the app dims.

The Puppet Master's first words ("Your effort to remain what you are...") are
authored whole by ConsoleWidget.__init__, so a console that never gets an intro
(tests, a headless build, any failure here) still carries the full line and its
summon link. The intro then REPLAYS that line: it blanks the block, dims
everything except the console, types the text back one character at a time, and
lifts the dim when the last character lands.

Nothing here can trap the user. The dim is a click-through overlay (the
Disturbance contract from seance.py: a plain overlay, no stylesheet swap, so
deleting it leaves the app exactly as it was), and any click or keypress ends
the intro at once with the whole line in place - which is also what keeps the
"redefine" link and its retire-the-line needle working mid-type.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QRegion, QTextCursor
from PySide6.QtWidgets import QApplication, QWidget


# Text the greeting block is found by. Present in the full line and nowhere
# else in a fresh console.
GREETING_NEEDLE = "Your effort to remain"

CARET = "▌"          # left half block: reads as a terminal caret


def markup_prefix(markup: str, n: int, link_re) -> str:
    """The first ``n`` VISIBLE characters of a [[label|url]] markup line, as
    markup. A link that is only partly revealed stays a link, so the label is
    underlined from its first letter instead of popping in at the end."""
    out = []
    pos = 0
    left = max(0, n)
    for m in link_re.finditer(markup):
        plain = markup[pos:m.start()]
        out.append(plain[:left])
        left -= min(left, len(plain))
        label, url = m.group(1), m.group(2)
        if left > 0:
            out.append(f"[[{label[:left]}|{url}]]")
            left -= min(left, len(label))
        pos = m.end()
    out.append(markup[pos:][:left])
    return "".join(out)


def visible_length(markup: str, link_re) -> int:
    return len(link_re.sub(lambda m: m.group(1), markup))


class Spotlight(QWidget):
    """Dim wash over the whole window with a hole where the console is."""

    WASH = QColor(4, 2, 8)      # the seance's failing-lights colour
    DEPTH = 0.62                # wash alpha at full strength

    def __init__(self, host, console):
        super().__init__(host)
        self._host = host
        self._console = console
        self.strength = 1.0     # 0..1, animated down on the way out
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        host.installEventFilter(self)
        self.sync()

    def sync(self):
        self.setGeometry(self._host.rect())
        self.raise_()

    def hole(self) -> QRect:
        """The console's rect in this overlay's coords (empty if hidden)."""
        console = self._console
        if console is None or not console.isVisible():
            return QRect()
        return QRect(console.mapTo(self._host, QPoint(0, 0)), console.size())

    def eventFilter(self, obj, event):
        if obj is getattr(self, '_host', None):
            if event.type() == QEvent.Type.Resize:
                self.sync()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        if self.strength <= 0.0:
            return
        painter = QPainter(self)
        painter.setClipRegion(QRegion(self.rect()) - QRegion(self.hole()))
        wash = QColor(self.WASH)
        wash.setAlphaF(self.DEPTH * min(1.0, self.strength))
        painter.fillRect(self.rect(), wash)
        painter.end()


class ConsoleIntro(QObject):
    """Drives the replay: blank -> dim -> type -> undim."""

    LEAD_IN_MS = 450        # let the window's 400ms fade-in land first
    CHAR_MS = 34
    PAUSE_MS = 260          # extra beat after . , ? ! so it reads as speech
    FADE_MS = 520
    FADE_STEP_MS = 16

    def __init__(self, console, host, markup: str, parent=None):
        super().__init__(parent or console)
        self._console = console
        self._host = host
        self._markup = markup
        self._total = visible_length(markup, console._LINK_MARKUP)
        self._plain = console._LINK_MARKUP.sub(lambda m: m.group(1), markup)
        self._shown = 0
        self._cursor = None
        self._spotlight = None
        self._running = False
        self._typer = QTimer(self)
        self._typer.setSingleShot(True)
        self._typer.timeout.connect(self._type_next)
        self._fader = QTimer(self)
        self._fader.setInterval(self.FADE_STEP_MS)
        self._fader.timeout.connect(self._fade_step)

    # -- lifecycle ---------------------------------------------------------
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Blank the greeting and begin. False (and nothing touched) if the
        greeting block cannot be found."""
        block = self._find_block()
        if block is None:
            return False
        cur = QTextCursor(block)
        cur.setKeepPositionOnInsert(True)
        self._cursor = cur
        self._running = True
        self._render(0)
        if self._host is not None:
            self._spotlight = Spotlight(self._host, self._console)
            self._spotlight.show()
        self._console.cleared.connect(self._on_cleared)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._typer.start(self.LEAD_IN_MS)
        return True

    def finish(self):
        """Land the whole line now and lift the dim (a click, a key, or the
        last character)."""
        if not self._running:
            return
        self._render(self._total, caret=False)
        self._stop_typing()
        self._fader.start()

    def _on_cleared(self):
        """/clear wiped the document mid-type: the block is gone, so do NOT
        write into whatever now sits at its old position."""
        if not self._running:
            return
        self._stop_typing()
        self._fader.start()

    def _stop_typing(self):
        self._running = False
        self._typer.stop()
        self._cursor = None
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        try:
            self._console.cleared.disconnect(self._on_cleared)
        except (RuntimeError, TypeError):
            pass

    # -- skip on any input -------------------------------------------------
    def eventFilter(self, obj, event):
        if getattr(self, '_running', False) and event.type() in (
                QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress):
            self.finish()
        return False    # never eat the event: the click still does its job

    # -- typing ------------------------------------------------------------
    def _find_block(self):
        block = self._console.output.document().firstBlock()
        while block.isValid():
            if GREETING_NEEDLE in block.text():
                return block
            block = block.next()
        return None

    def _render(self, n: int, caret: bool = True):
        if self._cursor is None:
            return
        console = self._console
        from techdeck.ui.theme_manager import get_theme_manager
        palette = get_theme_manager().get_current_palette()
        color = palette.console_text
        html = console.markup_to_html(
            markup_prefix(self._markup, n, console._LINK_MARKUP), color)
        tail = (f'<span style="color: {color};">{CARET}</span>'
                if caret else "")
        cur = QTextCursor(self._cursor)
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                         QTextCursor.MoveMode.KeepAnchor)
        cur.insertHtml(f'<span style="color: {color};">{html}</span>{tail}')
        self._shown = n

    def _type_next(self):
        if not self._running:
            return
        n = self._shown + 1
        if n >= self._total:
            self.finish()
            return
        self._render(n)
        typed = self._plain[n - 1]
        self._typer.start(
            self.CHAR_MS + (self.PAUSE_MS if typed in ".,?!" else 0))

    # -- undim -------------------------------------------------------------
    def _fade_step(self):
        spot = self._spotlight
        if spot is None:
            self._fader.stop()
            return
        spot.strength -= self.FADE_STEP_MS / self.FADE_MS
        if spot.strength <= 0.0:
            self._fader.stop()
            self._spotlight = None
            spot.hide()
            spot.deleteLater()
            return
        spot.update()
