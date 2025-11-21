# TechDeck Version Management Guide

## Overview
This guide explains how to properly manage version numbers across the TechDeck project to ensure consistency and traceability.

---

## Version Number Format

TechDeck follows **Semantic Versioning 2.0.0** (https://semver.org/):

```
MAJOR.MINOR.PATCH (e.g., 0.7.0)
```

- **MAJOR**: Incompatible API changes (0 = in development)
- **MINOR**: New features (backwards-compatible)
- **PATCH**: Bug fixes (backwards-compatible)

---

## Files That Must Be Updated

When releasing a new version, update **ALL** of these files:

### 1. `constants.py`
**Location:** `techdeck/core/constants.py`

```python
# Application metadata
APP_NAME = "TechDeck"
APP_VERSION = "0.7.0"  # <-- UPDATE THIS
APP_RELEASE_NAME = "Plugin Execution System"  # <-- UPDATE THIS
CONFIG_VERSION = "1.0.0"
```

**What to update:**
- `APP_VERSION`: The semantic version number
- `APP_RELEASE_NAME`: Short description of the release

---

### 2. `PROJECT_CHANGELOG.md`
**Location:** `PROJECT_CHANGELOG.md` (project root)

```markdown
**Last Updated:** 2025-10-30  
**Current Version:** v0.7.0 (Plugin Execution System)  # <-- UPDATE THIS
**Project Status:** 🟢 Active Development
```

**What to update:**
- Update the "Last Updated" date
- Update the "Current Version" line
- Add new version section with completed features
- Update version history table

---

### 3. `README.md` (Badge)
**Location:** `README.md` (project root)

```markdown
![TechDeck Logo](https://img.shields.io/badge/TechDeck-v0.7.0-blue?style=for-the-badge)
                                                            ^^^^^^
                                                        UPDATE THIS
```

---

### 4. Git Tags
After updating all files and committing:

```bash
git tag v0.7.0
git push origin v0.7.0
```

---

## Version Update Checklist

Before releasing a new version, complete this checklist:

### Pre-Release
- [ ] All features for this version are complete and tested
- [ ] All bugs for this version are fixed
- [ ] Documentation is up to date
- [ ] Version number follows semantic versioning rules

### Update Files
- [ ] Update `APP_VERSION` in `constants.py`
- [ ] Update `APP_RELEASE_NAME` in `constants.py`
- [ ] Update "Current Version" in `PROJECT_CHANGELOG.md`
- [ ] Update "Last Updated" date in `PROJECT_CHANGELOG.md`
- [ ] Add version history entry to `PROJECT_CHANGELOG.md`
- [ ] Update version badge in `README.md`
- [ ] Update any plugin version examples in documentation

### Testing
- [ ] Run application and verify version displays in Settings page
- [ ] Verify all features work as expected
- [ ] Check that no regressions were introduced

### Commit & Tag
- [ ] Commit all changes with descriptive message
- [ ] Create git tag: `git tag v0.X.Y`
- [ ] Push commits: `git push`
- [ ] Push tags: `git push --tags`

---

## Version Display Locations

The version number is displayed in these locations:

1. **Settings Page**: Shows "TechDeck v0.7.0 - Plugin Execution System"
2. **Window Title** (future): Will show in main window title bar
3. **About Dialog** (future): Will show detailed version info

---

## Deciding When to Increment

### PATCH (0.7.0 → 0.7.1)
Increment PATCH version when you:
- Fix bugs without changing features
- Update documentation only
- Make internal refactors that don't affect functionality
- Fix typos or UI polish

### MINOR (0.7.0 → 0.8.0)
Increment MINOR version when you:
- Add new features (new pages, new plugin capabilities)
- Add new UI components
- Introduce new functionality that users will notice
- Make improvements that change user workflows

### MAJOR (0.7.0 → 1.0.0)
Increment MAJOR version when you:
- Make breaking changes to plugin interface
- Change settings format (breaking old configs)
- Release production-ready version (0.x → 1.0)
- Completely redesign core features

**Note:** During 0.x development, we're more lenient with breaking changes.

---

## Version History Example

Here's how to add a new version to `PROJECT_CHANGELOG.md`:

```markdown
## 📈 Version History

| Version | Date | Description |
|---------|------|-------------|
| v0.8.0 | 2025-11-15 | Plugin settings system |
| v0.7.0 | 2025-10-30 | Plugin execution system |
| v0.6.0 | 2025-10-29 | Missing plugin handling |
```

---

## Plugin Versioning

Plugins should also follow semantic versioning in their `plugin.json`:

```json
{
  "id": "lst_organizer",
  "name": "LST Organizer",
  "version": "1.0.0",  // <-- Plugin version
  "author": "Your Name",
  "techdeck_version": "0.7.0"  // <-- Minimum TechDeck version required
}
```

**Plugin version rules:**
- Each plugin has its own independent version
- `techdeck_version` specifies minimum TechDeck version required
- Increment plugin version independently of TechDeck version

---

## Automated Version Checking (Future)

In future versions, TechDeck will:

1. **Auto-update checking**: Compare local version with server manifest
2. **Plugin compatibility**: Warn if plugin requires newer TechDeck version
3. **Version mismatch detection**: Alert if files are out of sync

Placeholder for this exists in `update_checker.py`.

---

## Common Mistakes to Avoid

❌ **Don't:**
- Forget to update `constants.py` (most common mistake!)
- Update only README but not CHANGELOG
- Skip git tags
- Use inconsistent version format (0.7 vs 0.7.0)
- Forget to update release name

✅ **Do:**
- Update ALL files listed above
- Use the checklist every time
- Test version display after updating
- Keep CHANGELOG up to date with features
- Create git tags for releases

---

## Quick Reference

**Current Version:** v0.7.0  
**Last Updated:** 2025-10-30  
**Next Planned:** v0.8.0 (Plugin Settings System)

**Files to Update:**
1. `techdeck/core/constants.py` → APP_VERSION, APP_RELEASE_NAME
2. `PROJECT_CHANGELOG.md` → Current Version, Last Updated, Version History
3. `README.md` → Version badge
4. Git tag → `v0.X.Y`

---

## Questions?

If you're unsure about versioning:
1. Check recent git history: `git log --oneline`
2. Review PROJECT_CHANGELOG.md for version patterns
3. When in doubt, increment MINOR version
4. Ask: "Will this break existing functionality?" → If yes, MAJOR. If no, MINOR.

---

**End of Version Management Guide**
