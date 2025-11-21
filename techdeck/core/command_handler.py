"""
TechDeck Command Handler
Processes console commands and returns responses.
NOW WITH: Fixed /clear and new /guides command!
"""

from typing import Callable
from pathlib import Path
from techdeck.core.settings import SettingsManager
from techdeck.core.constants import APP_VERSION


class CommandHandler:
    """
    Handles console commands.
    
    Commands:
        /help - Show available commands
        /clear - Clear console
        /version - Show TechDeck version
        /profiles - List all profiles
        /profile <name> - Switch to a profile
        /tiles - List tiles in current profile
        /theme <name> - Switch theme
        /guides - List available documentation guides
        /guide <name> - Show a specific guide
    """
    
    def __init__(self, settings: SettingsManager, console_widget):
        self.settings = settings
        self.console = console_widget
        
        # Command registry
        self.commands = {
            '/help': self._cmd_help,
            '/clear': self._cmd_clear,
            '/version': self._cmd_version,
            '/profiles': self._cmd_profiles,
            '/profile': self._cmd_switch_profile,
            '/tiles': self._cmd_tiles,
            '/theme': self._cmd_theme,
            '/guides': self._cmd_guides,
            '/guide': self._cmd_show_guide,
        }
    
    def handle_command(self, command_text: str) -> None:
        """
        Process a command and output result to console.
        
        Args:
            command_text: Full command string (including /)
        """
        parts = command_text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in self.commands:
            self.commands[cmd](args)
        else:
            self.console.append_error(f"Unknown command: {cmd}")
            self.console.append_system("Type /help for available commands.")
    
    def _cmd_help(self, args: str):
        """Show help message."""
        help_text = """Available commands:
  /help           - Show this help message
  /clear          - Clear console output
  /version        - Show TechDeck version
  /profiles       - List all profiles
  /profile <name> - Switch to a profile
  /tiles          - List tiles in current profile
  /theme <name>   - Switch theme (dark, light, blue)
  /guides         - List available documentation guides
  /guide <name>   - Show a specific guide"""
        
        self.console.append_system(help_text)
    
    def _cmd_clear(self, args: str):
        """Clear console output."""
        self.console.clear()
    
    def _cmd_version(self, args: str):
        """Show version info."""
        self.console.append_system(f"TechDeck v{APP_VERSION}")
    
    def _cmd_profiles(self, args: str):
        """List all profiles."""
        profiles = self.settings.get_profile_names()
        current = self.settings.get_current_profile_name()
        
        output = "Available profiles:"
        for profile in profiles:
            marker = " (current)" if profile == current else ""
            output += f"\n  â€¢ {profile}{marker}"
        
        self.console.append_system(output)
    
    def _cmd_switch_profile(self, args: str):
        """Switch to a profile."""
        if not args:
            self.console.append_error("Usage: /profile <name>")
            return
        
        profile_name = args.strip()
        
        if profile_name not in self.settings.get_profile_names():
            self.console.append_error(f"Profile '{profile_name}' not found.")
            self.console.append_system("Use /profiles to see available profiles.")
            return
        
        if self.settings.set_current_profile(profile_name):
            self.console.append_system(f"Switched to profile: {profile_name}")
            # Note: UI refresh would need to be wired up in shell
        else:
            self.console.append_error("Failed to switch profile.")
    
    def _cmd_tiles(self, args: str):
        """List tiles in current profile."""
        current = self.settings.get_current_profile_name()
        tiles = self.settings.get_profile_tiles()
        
        if not tiles:
            self.console.append_system(f"Profile '{current}' has no tiles.")
            return
        
        output = f"Tiles in '{current}':"
        for tile in tiles:
            output += f"\n  â€¢ {tile}"
        
        self.console.append_system(output)
    
    def _cmd_theme(self, args: str):
        """Switch theme."""
        if not args:
            current = self.settings.get_theme()
            self.console.append_system(f"Current theme: {current}")
            self.console.append_system("Available themes: dark, light, blue, salmon")
            self.console.append_system("Usage: /theme <name>")
            return
        
        theme_name = args.strip().lower()
        valid_themes = ["dark", "light", "blue", "salmon"]
        
        if theme_name not in valid_themes:
            self.console.append_error(f"Invalid theme: {theme_name}")
            self.console.append_system(f"Available themes: {', '.join(valid_themes)}")
            return
        
        self.settings.set_theme(theme_name)
        self.console.append_system(f"Theme changed to: {theme_name}")
        self.console.append_system("Restart TechDeck to apply the new theme.")
    
    def _cmd_guides(self, args: str):
        """List available documentation guides."""
        # Look for .md files in project root
        project_root = Path(__file__).parent.parent.parent
        
        guides = []
        guide_files = {
            "PLUGIN_DEVELOPER_GUIDE.md": "Plugin Developer Guide - How to create plugins",
            "PLUGIN_SYSTEM_IMPLEMENTATION.md": "Plugin System Implementation - Technical details",
            "TESTING_QUICK_START.md": "Testing Quick Start - How to test TechDeck",
            "README.md": "README - Project overview and setup",
        }
        
        output = "Available documentation guides:"
        for filename, description in guide_files.items():
            filepath = project_root / filename
            if filepath.exists():
                guide_name = filename.replace(".md", "").lower()
                output += f"\n  â€¢ {guide_name} - {description}"
                guides.append(guide_name)
        
        if guides:
            output += "\n\nUsage: /guide <name>"
            self.console.append_system(output)
        else:
            self.console.append_system("No documentation guides found in project root.")
    
    def _cmd_show_guide(self, args: str):
        """Show a specific guide."""
        if not args:
            self.console.append_error("Usage: /guide <name>")
            self.console.append_system("Use /guides to see available guides.")
            return
        
        guide_name = args.strip().lower()
        
        # Map guide names to filenames
        guide_map = {
            "plugin_developer_guide": "PLUGIN_DEVELOPER_GUIDE.md",
            "plugin_system_implementation": "PLUGIN_SYSTEM_IMPLEMENTATION.md",
            "testing_quick_start": "TESTING_QUICK_START.md",
            "readme": "README.md",
        }
        
        if guide_name not in guide_map:
            self.console.append_error(f"Guide '{guide_name}' not found.")
            self.console.append_system("Use /guides to see available guides.")
            return
        
        # Read and display the guide
        project_root = Path(__file__).parent.parent.parent
        guide_file = project_root / guide_map[guide_name]
        
        if not guide_file.exists():
            self.console.append_error(f"Guide file not found: {guide_map[guide_name]}")
            return
        
        try:
            with open(guide_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Display first 50 lines with a summary
            lines = content.split('\n')
            preview_lines = min(50, len(lines))
            
            self.console.append_system(f"=== {guide_map[guide_name]} ===")
            
            for line in lines[:preview_lines]:
                self.console.append_system(line)
            
            if len(lines) > preview_lines:
                self.console.append_system(f"\n... ({len(lines) - preview_lines} more lines)")
                self.console.append_system(f"Full guide at: {guide_file}")
            
        except Exception as e:
            self.console.append_error(f"Error reading guide: {e}")