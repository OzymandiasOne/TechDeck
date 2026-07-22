"""Tests for the pixel-style linter used by the Pixel Studio's Lint button."""


def _blank(n=8):
    return [[None] * n for _ in range(n)]


def test_analyze_counts_single_cluster():
    from tools.check_pixel_style import analyze
    C = (10, 20, 30, 255)
    grid = _blank()
    for y in (3, 4):
        for x in (3, 4):
            grid[y][x] = C          # one 2x2 block of one color
    a = analyze(grid)
    assert a["colors"] == 1
    assert a["orphans"] == []
    assert a["partial_alpha"] == []


def test_lint_flags_orphan_pixel(capsys):
    from tools.check_pixel_style import lint
    grid = _blank()
    grid[3][3] = (10, 20, 30, 255)   # a single isolated pixel -> orphan
    level = lint("t", grid, "logo")
    assert level == "FAIL"
    out = capsys.readouterr().out
    assert "orphan" in out.lower()


def test_lint_passes_a_real_generator_icon():
    from tools.check_pixel_style import lint, load_generator_key
    from tools.icon_editor import THEMED_SCRIPT
    grid = load_generator_key("badge", [THEMED_SCRIPT])
    level = lint("badge", grid, "logo")
    assert level in ("PASS", "WARN")   # a shipped icon must not FAIL the linter
