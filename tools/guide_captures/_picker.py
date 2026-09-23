"""Drive and photograph the Sentry Drone folder picker.

A folder pick is a NATIVE Windows dialog by default - a separate OS window that
a capture run (which renders offscreen) can neither grab nor drive. With the
Sentry Drone gadget owned and switched on for the app, the same pick opens as
``_ChopperDialog``: a QFileDialog with a HUD overlay, which IS a Qt widget. That
is why every folder-pick picture in the guide is the drone version, and why each
of those captions says so.

The 922 group scripts each grew their own copy of this driver. The 2026-09-23
folder-pick sweep needed it in the 911 scripts too, so it lives here once.

Usage - poll `tick()` from whatever step machine the calling script already has:

    pick = ChopperPick("select the 911 batch folder", "V060",
                       shots=["911_setup_batch_pick"])
    ...
    pick.tick()            # each timer tick
    if pick.done: ...
"""

from __future__ import annotations

import time

import capture_guide_screens as cam


class ChopperPick:
    """Lock a named folder, photograph the dialog + HUD, then fire or cancel.

    `title_sub`  - lower-case substring of the dialog title, so two pickers in
                   one run are never confused for each other.
    `folder`     - the row to lock, by exact name.
    `shots`      - image names to save the same composite under ([] = no shot).
    `mode`       - "fire" completes the pick (the run carries on), "cancel"
                   backs out of it.
    `sidebar_url`- shown as the only sidebar entry, so the capturing machine's
                   own Qt bookmarks stay out of the picture.
    `directory`  - point the dialog here first. Use it when the app opens the
                   pick at a real root the sandbox has no fixture under.
    """

    def __init__(self, title_sub: str, folder: str, shots=(), mode: str = "fire",
                 sidebar_url: str = "", resize=(640, 430), directory: str = ""):
        self.title_sub = title_sub.lower()
        self.folder = folder
        self.shots = list(shots)
        self.mode = mode
        self.sidebar_url = sidebar_url
        self.resize = resize
        # Where to point the dialog before locking. Needed whenever the app
        # opens the pick at a root the capture sandbox has no fixture under -
        # the real 911 QTDR, say - so `folder` would not be in the list.
        self.directory = directory
        self.step = 0
        self.t = 0.0
        self.done = False
        self._saved_sidebar = None

    # -- finding ------------------------------------------------------------
    def _dialog(self):
        from PySide6.QtWidgets import QApplication
        for w in QApplication.topLevelWidgets():
            if type(w).__name__ != "_ChopperDialog" or not w.isVisible():
                continue
            if self.title_sub in (w.windowTitle() or "").lower():
                return w
        return None

    def _row(self, dlg):
        """(view, index) of the row named `self.folder`, (view, None) while the
        model is still populating."""
        from PySide6.QtWidgets import QListView
        view = dlg.findChild(QListView, "listView")
        if view is None:
            return None, None
        model, root = view.model(), view.rootIndex()
        for r in range(model.rowCount(root)):
            idx = model.index(r, 0, root)
            if str(idx.data()) == self.folder:
                return view, idx
        return view, None

    # -- the step machine ---------------------------------------------------
    def tick(self):
        from PySide6.QtWidgets import QLineEdit, QPushButton
        now = time.time()
        dlg = self._dialog()
        if dlg is None:
            if self.step >= 5:          # finished and closed
                self.done = True
            return

        if self.step == 0:
            from PySide6.QtCore import QUrl
            if self.directory:
                dlg.setDirectory(self.directory)
            self._saved_sidebar = dlg.sidebarUrls()
            if self.sidebar_url:
                dlg.setSidebarUrls(
                    [QUrl.fromLocalFile(self.sidebar_url.replace("\\", "/"))])
            dlg.resize(*self.resize)
            geo = dlg._overlay.geometry() if dlg._overlay else None
            if geo is not None:
                dlg.move(geo.x() + (geo.width() - dlg.width()) // 2,
                         geo.y() + 110)
            self.step, self.t = 1, now

        elif self.step == 1 and now - self.t > 0.4:
            view, idx = self._row(dlg)
            if view is None or idx is None:
                return                  # model still populating - retry
            view.setCurrentIndex(idx)   # -> lock-on animation
            self.step, self.t = 2, now

        elif self.step == 2 and now - self.t > 1.0:
            view, idx = self._row(dlg)
            if idx is not None:
                dlg._on_click(idx)      # commit: TARGET CONFIRMED
            edit = dlg.findChild(QLineEdit, "fileNameEdit")
            if edit is not None:        # a real click fills this too
                edit.setText(self.folder)
            self.step, self.t = 3, now

        elif self.step == 3 and now - self.t > 0.8:
            if self.shots:
                composite(dlg, self.shots)
            # Restore before accept - accept persists the dialog state.
            dlg.setSidebarUrls(self._saved_sidebar or [])
            self.step, self.t = 4, now

        elif self.step == 4 and now - self.t > 0.3:
            want = "cancel" if self.mode == "cancel" else "execute"
            for b in dlg.findChildren(QPushButton):
                if b.text().replace("&", "").strip().lower() == want:
                    b.click()
                    break
            self.step, self.t = 5, now

        elif self.step == 5 and now - self.t > 0.35:
            ov = getattr(dlg, "_overlay", None)
            if ov is not None:
                ov.skip()               # jump the kill-cam to the close
            self.t = now                # keep nudging until the dialog closes


def composite(dlg, names) -> None:
    """Dialog + gunner HUD composited on the dark feed, cropped to the dialog
    plus the HUD strip above it, saved under every name in `names`."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor, QImage, QPainter

    ov = getattr(dlg, "_overlay", None)
    dpix = dlg.grab()
    cam.OUT_DIR.mkdir(parents=True, exist_ok=True)
    if ov is None:
        for n in names:
            dpix.save(str(cam.OUT_DIR / f"{n}.png"))
            print(f"  {n}.png (dialog only)", flush=True)
        return

    ogeo = ov.geometry()
    canvas = QImage(ogeo.width(), ogeo.height(),
                    QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor(8, 10, 8))
    p = QPainter(canvas)
    tl = dlg.mapToGlobal(QPoint(0, 0))
    dx, dy = tl.x() - ogeo.x(), tl.y() - ogeo.y()
    p.drawPixmap(dx, dy, dpix)
    p.drawPixmap(0, 0, ov.grab())
    p.end()

    x0 = max(0, dx - 80)
    x1 = min(ogeo.width(), dx + dpix.width() + 80)
    y1 = min(ogeo.height(), dy + dpix.height() + 56)
    crop = canvas.copy(x0, 0, x1 - x0, y1)
    for n in names:
        crop.save(str(cam.OUT_DIR / f"{n}.png"))
        print(f"  {n}.png  ({crop.width()}x{crop.height()})", flush=True)


def arm_drone(settings, plugin_ids) -> None:
    """Own the gadget and switch it on for `plugin_ids`, so their folder pick
    opens as a drivable Qt window instead of a native dialog."""
    settings.unlock_item("toy_sentry_drone")
    for pid in plugin_ids:
        settings.set_plugin_setting(pid, "sentry_drone", True)
