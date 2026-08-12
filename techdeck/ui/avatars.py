"""Round profile pictures, shared by the Assistant terminal and My Account.

Both places have to draw the *same* face, so the rendering lives here rather
than in either of them. Three sources, in the order the user's own picture
takes precedence:

1. a photo the user picked in My Account,
2. their initials on the theme accent (the Teams convention),
3. Woogy's Emporium sprite, for his side of the conversation.

Kept out of ``core/`` because it is all QPainter, and out of the Assistant
widgets because My Account is not allowed to reach into them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap

AVATAR_PX = 36

# A user's picture is normalised to this before it is stored, so a 12 MP phone
# photo doesn't end up living in the settings folder forever.
STORED_AVATAR_PX = 256

_WOOGY_DISC = "#4C3B6E"        # the Emporium's purple, so he sits on his own shelf

# Woogy's sprite is a full figure: three eyestalks and a mouth on top, and a
# striped bucket at his feet. A profile picture wants the face, so the bucket
# is cropped away before the circle is applied. Measured off the art, not
# guessed, and it is a FRACTION so re-drawing him at another size still lands
# on the face.
_WOOGY_FACE_FRACTION = 0.90


def circle_crop(source: QPixmap, size: int,
                backdrop: Optional[str] = None) -> QPixmap:
    """Centre-fill ``source`` into a circle of ``size`` px.

    ``backdrop`` paints a disc first, for art with a transparent background:
    a floating head with nothing behind it reads as a rendering glitch rather
    than an avatar.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    if backdrop:
        painter.fillPath(path, QColor(backdrop))
    if source is not None and not source.isNull():
        scaled = source.scaled(size, size,
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((size - scaled.width()) // 2,
                           (size - scaled.height()) // 2, scaled)
    painter.end()
    return pixmap


def woogy_avatar(size: int = AVATAR_PX) -> QPixmap:
    """Woogy's Emporium sprite as a round profile picture.

    The same ``.tdart`` asset the Emporium and the game use, so he is
    recognisably the same character everywhere.
    """
    try:
        from techdeck.ui import pixel_art
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS) / "assets" / "sprites"
        else:
            base = Path(__file__).resolve().parent.parent.parent / "assets" / "sprites"
        sprite = pixel_art.render(pixel_art.load(base / "woogy.tdart"), scale=1)
        # Smooth, not nearest: this is a ~36px downscale of a 71px sprite, and
        # a non-integer nearest-neighbour shrink drops whole rows of his eyes.
        face = sprite.copy(0, 0, sprite.width(),
                           max(1, int(sprite.height() * _WOOGY_FACE_FRACTION)))
    except Exception:
        face = QPixmap()

    if face.isNull():
        return _letter_avatar("W", _WOOGY_DISC, size)
    return circle_crop(face, size, backdrop=_WOOGY_DISC)


def initials_avatar(name: str, color: str, size: int = AVATAR_PX) -> QPixmap:
    """A coloured disc with someone's initials, the Teams convention."""
    return _letter_avatar(initials(name), color, size)


def _letter_avatar(text: str, color: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.fillPath(path, QColor(color))
    painter.setPen(QColor("#FFFFFF"))
    font = QFont()
    font.setPointSizeF(max(7.0, size * 0.38))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pixmap


def initials(name: str) -> str:
    """'Anthony Siebenmorgen' -> 'AS'. 'ASiebenmorgen' -> 'AS'."""
    words = [w for w in re.split(r"[\s._-]+", (name or "").strip()) if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        single = words[0]
        caps = re.findall(r"[A-Z]", single)
        if len(caps) >= 2:
            return (caps[0] + caps[1]).upper()
        return single[:2].upper()
    return "?"


def user_avatar(settings, name: str, color: str,
                size: int = AVATAR_PX) -> QPixmap:
    """The user's own face: their picture if they've set one, else initials.

    A picture that has been deleted or corrupted since it was chosen falls
    back to initials rather than showing a broken frame.
    """
    path = settings.avatar_path() if hasattr(settings, "avatar_path") else None
    if path and Path(path).exists():
        picture = QPixmap(str(path))
        if not picture.isNull():
            return circle_crop(picture, size)
    return initials_avatar(name, color, size)


def normalise_for_storage(source_path) -> Optional[QPixmap]:
    """Load a user-chosen image and shrink it to something worth keeping.

    Returns None if the file isn't a readable image, which is the answer for
    "they picked a PDF".
    """
    picture = QPixmap(str(source_path))
    if picture.isNull():
        return None
    if max(picture.width(), picture.height()) > STORED_AVATAR_PX:
        picture = picture.scaled(
            STORED_AVATAR_PX, STORED_AVATAR_PX,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
    return picture
