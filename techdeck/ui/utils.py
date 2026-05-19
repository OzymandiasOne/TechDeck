# utils.py
from pathlib import Path
import re
import hashlib
import tempfile

def make_tinted_svg_copy(src_svg_path: Path, color_hex: str) -> str:
    """
    Load an SVG file, replace any 'currentColor' (and explicit stroke/fill hex colors)
    with the given theme color, write a cached copy to the OS temp folder,
    and return a POSIX file path you can use in QSS `image: url(...)`.

    Returns: str (absolute path with forward slashes)
    """
    src = Path(src_svg_path)
    if not src.exists():
        raise FileNotFoundError(f"SVG not found: {src}")

    svg = src.read_text(encoding="utf-8")

    # Normalize color like '#AABBCC' or '#ABC'
    color = color_hex.strip()
    if not color.startswith("#") or len(color) not in (4, 7):
        raise ValueError(f"Bad color hex: {color_hex}")

    # Replace 'currentColor' and any explicit hex stroke/fill with theme color
    svg = svg.replace("currentColor", color)
    svg = re.sub(r'(stroke|fill)="#[0-9A-Fa-f]{3,6}"', rf'\1="{color}"', svg)

    # Cache file name based on source path + color so we reuse per theme
    key = f"{str(src.resolve())}|{color}"
    stamp = hashlib.md5(key.encode("utf-8")).hexdigest()[:8]
    out_name = f"{src.stem}-{stamp}.svg"

    out_dir = Path(tempfile.gettempdir()) / "techdeck_svg_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name
    out_path.write_text(svg, encoding="utf-8")

    return out_path.as_posix()
