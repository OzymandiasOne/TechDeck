"""Windows desktop notifications, via Qt's own tray icon.

``QSystemTrayIcon.showMessage`` hands the text to the real Windows notification
centre. It was chosen over ``winotify`` / ``win10toast`` / ``windows-toasts``
for one reason that outranks their extra features: **it adds no dependency**.
TechDeck ships into an environment where users cannot install anything, so
every third-party package is one more thing to force into ``TechDeck.spec``
and one more thing that can fail on a locked-down machine. PySide6 is already
bundled, and the API is present and supported there (verified before this was
written: ``isSystemTrayAvailable()`` and ``supportsMessages()`` both True).

**The trade-off, stated plainly:** notifications only fire while TechDeck is
running. Reminders that must survive the app being closed belong on the real
calendar, which is what the Assistant's `.ics` export is for.

Everything degrades quietly. No tray, no notification, no crash, and the
settings dialog says so rather than pretending it worked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QSystemTrayIcon
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon


def _app_icon() -> QIcon:
    root = Path(__file__).resolve().parent.parent.parent
    path = root / "assets" / "TechDeck.ico"
    return QIcon(str(path)) if path.exists() else QIcon()


class DesktopNotifier(QObject):
    """Owns the tray icon and turns text into a Windows toast.

    The tray icon is created lazily and only exists while notifications are
    switched on: an icon sitting in the tray implies the app is doing something
    in the background, and when reminders are off it isn't.
    """

    activated = Signal()          # the user clicked the notification

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._tray: Optional[QSystemTrayIcon] = None

    # -- availability --------------------------------------------------------

    @staticmethod
    def available() -> bool:
        """Can this machine show a desktop notification at all?"""
        try:
            return (QSystemTrayIcon.isSystemTrayAvailable()
                    and QSystemTrayIcon.supportsMessages())
        except Exception:
            return False

    @staticmethod
    def unavailable_reason() -> str:
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return "Windows isn't offering a notification area on this machine."
            if not QSystemTrayIcon.supportsMessages():
                return "This machine's notification area can't show messages."
        except Exception as exc:
            return f"Notifications aren't available here ({exc})."
        return ""

    # -- lifecycle -----------------------------------------------------------

    def set_enabled(self, enabled: bool):
        if enabled:
            self._ensure_tray()
        elif self._tray is not None:
            self._tray.hide()
            self._tray.deleteLater()
            self._tray = None

    def _ensure_tray(self) -> Optional[QSystemTrayIcon]:
        if self._tray is not None:
            return self._tray
        if not self.available():
            return None
        try:
            tray = QSystemTrayIcon(_app_icon(), self)
            tray.setToolTip("TechDeck")
            tray.messageClicked.connect(self.activated.emit)
            tray.activated.connect(lambda _reason: self.activated.emit())
            tray.show()
        except Exception as exc:
            print(f"[notifier] could not create the tray icon: {exc}")
            return None
        self._tray = tray
        return tray

    # -- sending -------------------------------------------------------------

    def notify(self, title: str, body: str, seconds: int = 12) -> bool:
        """Show one notification. Returns False if it couldn't be shown.

        Never raises: a reminder failing is not worth taking the page down for.
        """
        tray = self._ensure_tray()
        if tray is None:
            return False
        try:
            tray.showMessage(str(title), str(body), _app_icon(),
                             max(1, int(seconds)) * 1000)
            return True
        except Exception as exc:
            print(f"[notifier] showMessage failed: {exc}")
            return False
