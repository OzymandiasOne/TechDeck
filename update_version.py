#!/usr/bin/env python3
"""
TechDeck Version Update Script

Automates updating version numbers across all project files.
Run this script whenever you're ready to release a new version.

Usage:
    python update_version.py 0.8.0 "Plugin Settings System"
    python update_version.py 0.7.1 "Bug fixes"
"""

import sys
import re
from pathlib import Path
from datetime import datetime


def update_constants_py(version: str, release_name: str, project_root: Path) -> bool:
    """Update APP_VERSION and APP_RELEASE_NAME in constants.py"""
    constants_path = project_root / "techdeck" / "core" / "constants.py"
    
    if not constants_path.exists():
        print(f"❌ Error: {constants_path} not found")
        return False
    
    content = constants_path.read_text(encoding="utf-8")
    
    # Update APP_VERSION
    content = re.sub(
        r'APP_VERSION = "[^"]*"',
        f'APP_VERSION = "{version}"',
        content
    )
    
    # Update APP_RELEASE_NAME
    content = re.sub(
        r'APP_RELEASE_NAME = "[^"]*"',
        f'APP_RELEASE_NAME = "{release_name}"',
        content
    )
    
    constants_path.write_text(content, encoding="utf-8")
    print(f"✅ Updated: {constants_path}")
    return True


def update_changelog(version: str, release_name: str, project_root: Path) -> bool:
    """Update PROJECT_CHANGELOG.md with new version and date"""
    changelog_path = project_root / "PROJECT_CHANGELOG.md"
    
    if not changelog_path.exists():
        print(f"❌ Error: {changelog_path} not found")
        return False
    
    content = changelog_path.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Update Last Updated date
    content = re.sub(
        r'\*\*Last Updated:\*\* \d{4}-\d{2}-\d{2}',
        f'**Last Updated:** {today}',
        content
    )
    
    # Update Current Version
    content = re.sub(
        r'\*\*Current Version:\*\* v[\d.]+ \([^)]+\)',
        f'**Current Version:** v{version} ({release_name})',
        content
    )
    
    changelog_path.write_text(content, encoding="utf-8")
    print(f"✅ Updated: {changelog_path}")
    print(f"⚠️  Don't forget to manually add version history entry in {changelog_path}!")
    return True


def update_readme_badge(version: str, project_root: Path) -> bool:
    """Update version badge in README.md"""
    readme_path = project_root / "README.md"
    
    if not readme_path.exists():
        print(f"❌ Error: {readme_path} not found")
        return False
    
    content = readme_path.read_text(encoding="utf-8")
    
    # Update badge
    content = re.sub(
        r'TechDeck-v[\d.]+-blue',
        f'TechDeck-v{version}-blue',
        content
    )
    
    readme_path.write_text(content, encoding="utf-8")
    print(f"✅ Updated: {readme_path}")
    return True


def validate_version(version: str) -> bool:
    """Validate that version follows semantic versioning"""
    pattern = r'^\d+\.\d+\.\d+$'
    if not re.match(pattern, version):
        print(f"❌ Error: Version '{version}' doesn't follow semantic versioning (X.Y.Z)")
        return False
    return True


def print_next_steps(version: str):
    """Print remaining manual steps"""
    print("\n" + "="*60)
    print("📋 NEXT STEPS:")
    print("="*60)
    print("\n1. Review changes in git:")
    print("   git diff")
    print("\n2. Add version history entry to PROJECT_CHANGELOG.md:")
    print(f"   | v{version} | {datetime.now().strftime('%Y-%m-%d')} | Description here |")
    print("\n3. Test the application:")
    print("   python -m techdeck")
    print("   - Check Settings page shows correct version")
    print("   - Verify all features work")
    print("\n4. Commit and tag:")
    print("   git add .")
    print(f"   git commit -m 'Release v{version}'")
    print(f"   git tag v{version}")
    print("   git push")
    print("   git push --tags")
    print("\n" + "="*60)


def main():
    if len(sys.argv) != 3:
        print("Usage: python update_version.py <version> <release_name>")
        print('Example: python update_version.py 0.8.0 "Plugin Settings System"')
        sys.exit(1)
    
    version = sys.argv[1]
    release_name = sys.argv[2]
    
    # Validate version format
    if not validate_version(version):
        sys.exit(1)
    
    # Get project root (script should be in project root)
    project_root = Path(__file__).parent
    
    print(f"\n🚀 Updating TechDeck to v{version} - {release_name}")
    print("="*60 + "\n")
    
    # Update all files
    success = True
    success &= update_constants_py(version, release_name, project_root)
    success &= update_changelog(version, release_name, project_root)
    success &= update_readme_badge(version, project_root)
    
    if success:
        print(f"\n✅ All files updated successfully!")
        print_next_steps(version)
    else:
        print("\n❌ Some updates failed. Please review errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
