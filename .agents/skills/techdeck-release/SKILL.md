---
name: techdeck-release
description: Prep a TechDeck release locally — bump the version, run the PyInstaller + Inno Setup build, test the exe, make a local commit + tag, and draft the auto-updater manifest description. Use when asked to release, build the installer, ship a new version, or bump TechDeck's version number.
---

# Cutting a TechDeck release

TechDeck ships as a standalone Windows exe (PyInstaller + Inno Setup) via GitHub Releases
with an auto-updater. Releases are built **locally**, not in CI.

> **Codex does LOCAL steps only — never touch GitHub.** Do NOT `git push`, do NOT use `gh`,
> do NOT fetch/read/edit the updates manifest, and do NOT create or upload GitHub Releases.
> The user does ALL GitHub work manually (push, Release upload, manifest). Codex's job ends
> at: version bump → build → test → local commit + tag → hand the user a manifest description
> to paste. If you think a step needs GitHub, stop and hand it to the user instead.

The local build is the source of truth; the `origin/main` remote lags behind the shipped
code, and that's fine — leave it to the user.

## 1. Bump the version (every place)

**ASK THE USER for the new version number before touching anything — never pick it
yourself.** The user owns the numbering scheme, and a wrong guess means redoing the
bump, the workbook row, the build, the commit, and the tag (this happened: Codex
chose 0.8.6 when the user wanted 0.8.5.5). First question of every release:
"What version number is this release?"

Then update the given number in ALL of:
- `techdeck/core/constants.py` — `APP_VERSION` (and optionally the trailing patch-description comment).
- `TechDeck-Setup.iss` — **TWO** spots: the leading `; Version X.Y.Z` comment AND
  `#define MyAppVersion "X.Y.Z"`.
- `README.md` — the title / "current version" line.

A version bump is also the trigger for the **management-facing** doc (see AGENTS.md
Documentation Update Protocol): add one VERSION HISTORY row to
`TechDeck Version Controller.xlsx` and update AUTOMATION TOOLS rows if a tool changed.
Use business framing (time saved, automation scope, reliability); never mention the
toolchain or easter eggs there.

## 2. Build

```
.\build.ps1
```
Cleans `dist/`, runs PyInstaller, verifies assets, runs Inno Setup.
Output: `installer_output\TechDeck-{version}-Setup.exe`

Build-time Hard Rules:
- **`build.ps1` must be ASCII only** — Unicode symbols (checkmarks, emoji, arrows) cause
  PowerShell parser errors on some machines.
- **PyInstaller asset inclusion** — every non-Python asset dir must be in the `datas` list
  in `TechDeck.spec` (currently `('assets','assets')`, `('plugins','plugins')`). A new
  asset directory that's not listed is missing in the build.
- **Hidden imports** — anything imported only inside a plugin's `run.py` must be in
  `hiddenimports` in `TechDeck.spec`: third-party libs (openpyxl, pandas, fitz, pypdf,
  qrcode+submodules, PIL+submodules, `PySide6.QtCharts`) AND first-party modules the main
  app never imports (`techdeck.core.plugin_sdk`, `techdeck.core.plugin_window` — the
  latter's omission broke Customer DXF Quoting in the v0.8.6 build). If a plugin works in
  dev but errors with a missing module in the built exe, add the module here.
- **Ship-readiness gate** — `build.ps1` step [3/7] runs
  `python tools\check_ship_readiness.py --load` and aborts the build on any error, so
  hiddenimports/manifest misses can't ship. It can be run standalone any time; the
  checklist behind it is `docs/PLUGIN_SHIP_REQUIREMENTS.md`.

## 3. Test the frozen build

Run `dist\TechDeck\TechDeck.exe` and smoke-test the changed areas (and any plugin that
uses a newly added third-party lib — those only fail in the frozen build).

## 4. Local commit + tag (NO push)

```
git add . && git commit -m "Release vX.Y.Z" && git tag vX.Y.Z
```
Stop here. **Do not push.** The user pushes and tags on GitHub themselves.

## 5. Draft the manifest description (do NOT publish it)

Write the release-notes / description text for `manifest.json` and give it to the user to
paste. Codex never opens, fetches, or edits the live manifest. Because the boundary of
"what last shipped" can be fuzzy (the version number sometimes stays put across many
commits), confirm with the user what the previous shipped build contained rather than
assuming the git tag is the boundary.

## Checklist (Codex's local scope)

- [ ] **Version number asked of and given by the user** (never self-chosen)
- [ ] Version bumped in constants.py, TechDeck-Setup.iss (×2), README.md
- [ ] Version Controller.xlsx VERSION HISTORY row added (business framing)
- [ ] `.\build.ps1` succeeded; installer produced
- [ ] `dist\TechDeck\TechDeck.exe` smoke-tested (incl. plugins using new libs)
- [ ] Local commit + tag `vX.Y.Z` made (NOT pushed)
- [ ] Manifest description drafted and handed to the user

## Handed off to the user (manual, on GitHub — Codex does not do these)

- [ ] `git push` + `git push --tags`
- [ ] GitHub Release created, installer attached
- [ ] `manifest.json` updated on TechDeck-updates
