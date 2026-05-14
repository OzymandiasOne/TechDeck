"""
TechDeck Command Handler
Processes console commands and returns responses.
"""

import random
import re
import socket
import threading
from typing import Callable
from pathlib import Path
from techdeck.core.settings import SettingsManager
from techdeck.core.constants import APP_VERSION
from techdeck.core.flavor import CompendiumState, COMPLIMENTS, ROASTS, generate_haiku


class CommandHandler:
    """
    Handles console commands.

    Commands:
        /help           - Show available commands
        /clear          - Clear console
        /version        - Show TechDeck version
        /profiles       - List all profiles
        /profile <name> - Switch to a profile
        /tiles          - List tiles in current profile
        /theme <name>   - Switch theme
        /guides         - List available documentation guides
        /guide <name>   - Show a specific guide
        /fidget         - Open fidget spinner window
        /rave           - Pulse accent colors for 10 seconds
        /jack           - Play blackjack in the console
        /compliment     - Receive a compliment
        /roast          - Receive a roast
        /haiku          - Print a manufacturing haiku
        /moth           - Summon a moth toward the Run button
    """

    def __init__(self, settings: SettingsManager, console_widget, main_window=None):
        self.settings = settings
        self.console = console_widget
        self.main_window = main_window

        # Personality pools
        self._compliments = CompendiumState(COMPLIMENTS)
        self._roasts = CompendiumState(ROASTS)

        # Runtime state
        self._rave_timer = None
        self._rave_step = 0
        self._moth = None
        self._moth_targets = []  # cycled through on repeat /moth calls
        self._moth_target_idx = 0
        self._jack_running = False
        self._mud_connected = False
        self._mud_session = None

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
            '/darkerrealms': self._cmd_darkerrealms,
            '/fidget': self._cmd_fidget,
            '/rave': self._cmd_rave,
            '/jack': self._cmd_jack,
            '/compliment': self._cmd_compliment,
            '/roast': self._cmd_roast,
            '/haiku': self._cmd_haiku,
            '/moth': self._cmd_moth,
        }

    def handle_command(self, command_text: str) -> None:
        parts = command_text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in self.commands:
            self.commands[cmd](args)
        else:
            self.console.append_error(f"Unknown command: {cmd}")
            self.console.append_system("Type /help for available commands.")

    # ------------------------------------------------------------------ #
    #  Core commands
    # ------------------------------------------------------------------ #

    def _cmd_help(self, args: str):
        help_text = """Available commands:
  /help           - Show this help message
  /clear          - Clear console output
  /version        - Show TechDeck version
  /profiles       - List all profiles
  /profile <name> - Switch to a profile
  /tiles          - List tiles in current profile
  /theme <name>   - Switch theme (dark, light, blue, salmon)
  /guides         - List documentation guides
  /guide <name>   - Show a specific guide

  /darkerrealms
  /fidget
  /rave
  /jack
  /compliment
  /roast
  /haiku
  /moth"""
        self.console.append_system(help_text)

    def _cmd_clear(self, args: str):
        self.console.clear()

    def _cmd_version(self, args: str):
        self.console.append_system(f"TechDeck v{APP_VERSION}")

    def _cmd_profiles(self, args: str):
        profiles = self.settings.get_profile_names()
        current = self.settings.get_current_profile_name()
        output = "Available profiles:"
        for profile in profiles:
            marker = " (current)" if profile == current else ""
            output += f"\n  • {profile}{marker}"
        self.console.append_system(output)

    def _cmd_switch_profile(self, args: str):
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
        else:
            self.console.append_error("Failed to switch profile.")

    def _cmd_tiles(self, args: str):
        current = self.settings.get_current_profile_name()
        tiles = self.settings.get_profile_tiles()
        if not tiles:
            self.console.append_system(f"Profile '{current}' has no tiles.")
            return
        output = f"Tiles in '{current}':"
        for tile in tiles:
            output += f"\n  • {tile}"
        self.console.append_system(output)

    def _cmd_theme(self, args: str):
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
        project_root = Path(__file__).parent.parent.parent
        guide_files = {
            "PLUGIN_DEVELOPER_GUIDE.md": "Plugin Developer Guide",
            "PLUGIN_SYSTEM_IMPLEMENTATION.md": "Plugin System Implementation",
            "TESTING_QUICK_START.md": "Testing Quick Start",
            "README.md": "README",
        }
        output = "Available documentation guides:"
        guides = []
        for filename, description in guide_files.items():
            filepath = project_root / filename
            if filepath.exists():
                guide_name = filename.replace(".md", "").lower()
                output += f"\n  • {guide_name} - {description}"
                guides.append(guide_name)
        if guides:
            output += "\n\nUsage: /guide <name>"
            self.console.append_system(output)
        else:
            self.console.append_system("No documentation guides found.")

    def _cmd_show_guide(self, args: str):
        if not args:
            self.console.append_error("Usage: /guide <name>")
            return
        guide_name = args.strip().lower()
        guide_map = {
            "plugin_developer_guide": "PLUGIN_DEVELOPER_GUIDE.md",
            "plugin_system_implementation": "PLUGIN_SYSTEM_IMPLEMENTATION.md",
            "testing_quick_start": "TESTING_QUICK_START.md",
            "readme": "README.md",
        }
        if guide_name not in guide_map:
            self.console.append_error(f"Guide '{guide_name}' not found.")
            return
        project_root = Path(__file__).parent.parent.parent
        guide_file = project_root / guide_map[guide_name]
        if not guide_file.exists():
            self.console.append_error(f"Guide file not found: {guide_map[guide_name]}")
            return
        try:
            with open(guide_file, 'r', encoding='utf-8') as f:
                content = f.read()
            lines = content.split('\n')
            preview = min(50, len(lines))
            self.console.append_system(f"=== {guide_map[guide_name]} ===")
            for line in lines[:preview]:
                self.console.append_system(line)
            if len(lines) > preview:
                self.console.append_system(f"\n... ({len(lines) - preview} more lines)")
                self.console.append_system(f"Full guide at: {guide_file}")
        except Exception as e:
            self.console.append_error(f"Error reading guide: {e}")

    # ------------------------------------------------------------------ #
    #  /darkerrealms  — MUD client
    # ------------------------------------------------------------------ #

    _MUD_HOST = "darkerrealms.org"
    _MUD_PORT = 2000
    _ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFABCDJst]|\x1b[=>]|\x1b\([A-Z]|\x1b[A-Z]')

    def _cmd_darkerrealms(self, args: str):
        if self._mud_connected:
            self.console.append_system("Already connected. Type 'quit' in-game to disconnect.")
            return
        t = threading.Thread(
            target=self._mud_session_loop, daemon=True, name="MudSession"
        )
        t.start()
        self._mud_session = t

    def _mud_session_loop(self):
        log = self.console.safe_game_log
        ask = self.console.request_input

        log(f"Connecting to {self._MUD_HOST}:{self._MUD_PORT}...")
        try:
            sock = socket.create_connection((self._MUD_HOST, self._MUD_PORT), timeout=15)
        except Exception as e:
            log(f"Connection failed: {e}")
            return

        self._mud_connected = True
        log("Connected. Your commands are echoed above each reply.")
        log("Type 'quit' in-game to disconnect from the MUD.")

        # Reader thread — receives server output and pushes to console
        reader = threading.Thread(
            target=self._mud_reader, args=(sock, log), daemon=True, name="MudReader"
        )
        reader.start()

        try:
            while self._mud_connected:
                # Silent input (empty prompt) — no "Type your response below" noise
                cmd = ask("")
                if not self._mud_connected:
                    break
                try:
                    sock.sendall((cmd + "\r\n").encode("utf-8", errors="replace"))
                except OSError:
                    break
        finally:
            self._mud_connected = False
            try:
                sock.close()
            except OSError:
                pass
            log("Disconnected from Darker Realms.")

    def _mud_reader(self, sock: socket.socket, log):
        buf = ""
        while self._mud_connected:
            try:
                raw = sock.recv(4096)
                if not raw:
                    break
                # Process Telnet negotiation and get cleaned text + responses to send back
                cleaned, responses = self._process_telnet(raw)
                if responses:
                    try:
                        sock.sendall(responses)
                    except OSError:
                        break
                text = cleaned.decode("utf-8", errors="replace")
                text = self._ANSI_RE.sub("", text)
                buf += text
                lines = buf.split("\n")
                buf = lines[-1]
                for line in lines[:-1]:
                    line = line.rstrip("\r")
                    if line:
                        log(line)
                # Flush promptlike output that won't end in a newline
                if buf.rstrip("\r"):
                    log(buf.rstrip("\r"))
                    buf = ""
            except OSError:
                break

        if self._mud_connected:
            log("Connection closed by server. Press Enter to exit.")
            self._mud_connected = False

    @staticmethod
    def _process_telnet(data: bytes) -> tuple[bytes, bytes]:
        """
        Parse raw Telnet data. Strip IAC sequences from display output and
        build polite DONT/WONT negotiation responses so the server doesn't
        time us out waiting for a handshake reply.
        """
        IAC  = 0xFF
        WILL = 0xFB
        WONT = 0xFC
        DO   = 0xFD
        DONT = 0xFE

        result    = bytearray()
        responses = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b == IAC:
                if i + 1 < len(data):
                    cmd = data[i + 1]
                    if cmd == WILL and i + 2 < len(data):
                        # Server says it WILL do X → reply DONT X
                        responses += bytes([IAC, DONT, data[i + 2]])
                        i += 3
                    elif cmd == DO and i + 2 < len(data):
                        # Server asks us to DO X → reply WONT X
                        responses += bytes([IAC, WONT, data[i + 2]])
                        i += 3
                    elif cmd in (WONT, DONT) and i + 2 < len(data):
                        i += 3  # acknowledgement only, no reply needed
                    elif cmd == IAC:
                        result.append(IAC)  # escaped 0xFF literal
                        i += 2
                    else:
                        i += 2
                else:
                    i += 1
            else:
                result.append(b)
                i += 1
        return bytes(result), bytes(responses)

    # ------------------------------------------------------------------ #
    #  /fidget
    # ------------------------------------------------------------------ #

    def _cmd_fidget(self, args: str):
        from techdeck.ui.widgets.fidget_spinner import FidgetSpinnerWindow
        spinner = FidgetSpinnerWindow()
        # Center on screen
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        spinner.move(
            screen.center().x() - spinner.width() // 2,
            screen.center().y() - spinner.height() // 2,
        )
        spinner.show()
        # Keep alive (store on handler to prevent GC)
        self._spinner = spinner
        self.console.append_system("Double-click the spinner to close it.")

    # ------------------------------------------------------------------ #
    #  /rave
    # ------------------------------------------------------------------ #

    _RAVE_COLORS = [
        "#FF2080", "#FF8000", "#FFE000", "#00E060",
        "#00CFFF", "#5050FF", "#CC00FF", "#FF2080",
    ]

    def _cmd_rave(self, args: str):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        from techdeck.ui.theme import THEMES, generate_stylesheet

        if self._rave_timer is not None:
            self.console.append_system("Already raving.")
            return

        app = QApplication.instance()
        if app is None:
            return

        theme_name = self.settings.get_theme()
        if theme_name not in THEMES:
            theme_name = "dark"

        # Save originals
        orig_accent = THEMES[theme_name].accent
        orig_hover = THEMES[theme_name].accent_hover
        orig_pressed = THEMES[theme_name].accent_pressed

        elapsed = [0]
        step = [0]

        def tick():
            elapsed[0] += 150
            if elapsed[0] >= 10_000:
                THEMES[theme_name].accent = orig_accent
                THEMES[theme_name].accent_hover = orig_hover
                THEMES[theme_name].accent_pressed = orig_pressed
                app.setStyleSheet(generate_stylesheet(theme_name))
                self._rave_timer.stop()
                self._rave_timer = None
                self.console.append_system("Rave over. Back to work.")
                return

            color = self._RAVE_COLORS[step[0] % len(self._RAVE_COLORS)]
            step[0] += 1
            THEMES[theme_name].accent = color
            THEMES[theme_name].accent_hover = color
            THEMES[theme_name].accent_pressed = color
            app.setStyleSheet(generate_stylesheet(theme_name))

        self._rave_timer = QTimer()
        self._rave_timer.setInterval(150)
        self._rave_timer.timeout.connect(tick)
        self._rave_timer.start()
        self.console.append_game("Let's rave.")

    # ------------------------------------------------------------------ #
    #  /jack  — Blackjack
    # ------------------------------------------------------------------ #

    DEALER_NAME = "Sal"
    JACK_BET = 25

    def _cmd_jack(self, args: str):
        if self._jack_running:
            self.console.append_system("Sal is still waiting on you.")
            return
        self._jack_running = True
        t = threading.Thread(target=self._jack_game_loop, daemon=True, name="BlackjackGame")
        t.start()

    def _jack_game_loop(self):
        log = self.console.safe_game_log
        ask = self.console.request_input

        bankroll = self.settings.get_blackjack_bankroll()
        bet = self.JACK_BET

        log("")
        log(f"  -- BLACKJACK with {self.DEALER_NAME} --")
        log(f"  Bankroll: ${bankroll}   Bet: ${bet} per hand")
        log(f"  Commands: hit  stand  double  quit")
        log("")

        try:
            while True:
                if bankroll <= 0:
                    log(f"  {self.DEALER_NAME}: You're broke. Here's $100. Don't.")
                    bankroll = 100
                    self.settings.set_blackjack_bankroll(bankroll)

                if bankroll < bet:
                    log(f"  Not enough for a full bet. Bankroll: ${bankroll}")
                    break

                # --- Deal ---
                deck = self._new_deck()
                player = [deck.pop(), deck.pop()]
                dealer = [deck.pop(), deck.pop()]

                player_total = self._hand_total(player)
                dealer_total = self._hand_total(dealer)

                log(f"  {self.DEALER_NAME}:  {self._hand_str([dealer[0]], hide_second=True)}")
                log(f"  You:   {self._hand_str(player)}  --  {player_total}")

                # Player blackjack
                if player_total == 21 and len(player) == 2:
                    log(f"  {self.DEALER_NAME}:  {self._hand_str(dealer)}  --  {dealer_total}")
                    if dealer_total == 21 and len(dealer) == 2:
                        log(f"  Push. Both blackjack.")
                    else:
                        winnings = int(bet * 1.5)
                        bankroll += winnings
                        log(f"  Blackjack. +${winnings}   Bankroll: ${bankroll}")
                        log(f"  {self.DEALER_NAME}: Nice hand.")
                    self.settings.set_blackjack_bankroll(bankroll)
                    resp = ask("  Play again? (yes / no)").strip().lower()
                    if resp not in ("yes", "y"):
                        break
                    log("")
                    continue

                # Player turn
                doubled = False
                while True:
                    resp = ask(f"  >").strip().lower()

                    if resp == "quit":
                        log(f"  {self.DEALER_NAME}: Come back when you're ready.")
                        self.settings.set_blackjack_bankroll(bankroll)
                        self._jack_running = False
                        return

                    if resp in ("h", "hit"):
                        player.append(deck.pop())
                        player_total = self._hand_total(player)
                        log(f"  You:   {self._hand_str(player)}  --  {player_total}")
                        if player_total > 21:
                            log(f"  Bust. -${bet}   Bankroll: ${bankroll - bet}")
                            bankroll -= bet
                            self.settings.set_blackjack_bankroll(bankroll)
                            log(f"  {self.DEALER_NAME}: {random.choice(['Happens.', 'Too many.', 'Rough.'])}")
                            break

                    elif resp in ("s", "stand"):
                        break

                    elif resp in ("d", "double"):
                        if bankroll >= bet * 2:
                            doubled = True
                            player.append(deck.pop())
                            player_total = self._hand_total(player)
                            log(f"  You:   {self._hand_str(player)}  --  {player_total}  (doubled)")
                            if player_total > 21:
                                log(f"  Bust. -${bet * 2}   Bankroll: ${bankroll - bet * 2}")
                                bankroll -= bet * 2
                                self.settings.set_blackjack_bankroll(bankroll)
                                log(f"  {self.DEALER_NAME}: Brave.")
                            break
                        else:
                            log(f"  Not enough bankroll to double.")
                    else:
                        log(f"  hit / stand / double / quit")

                if player_total > 21:
                    resp = ask("  Play again? (yes / no)").strip().lower()
                    if resp not in ("yes", "y"):
                        break
                    log("")
                    continue

                # Dealer turn
                log(f"  {self.DEALER_NAME}:  {self._hand_str(dealer)}  --  {dealer_total}")
                while dealer_total < 17 or (dealer_total == 17 and self._is_soft_17(dealer)):
                    dealer.append(deck.pop())
                    dealer_total = self._hand_total(dealer)
                    log(f"  {self.DEALER_NAME}:  {self._hand_str(dealer)}  --  {dealer_total}")

                effective_bet = bet * 2 if doubled else bet

                if dealer_total > 21:
                    bankroll += effective_bet
                    log(f"  Dealer bust. +${effective_bet}   Bankroll: ${bankroll}")
                    log(f"  {self.DEALER_NAME}: {random.choice(['Good for you.', 'You win.', 'Fine.'])}")
                elif player_total > dealer_total:
                    bankroll += effective_bet
                    log(f"  You win. +${effective_bet}   Bankroll: ${bankroll}")
                    log(f"  {self.DEALER_NAME}: {random.choice(['Nice.', 'Well played.', 'You got lucky.'])}")
                elif dealer_total > player_total:
                    bankroll -= effective_bet
                    log(f"  {self.DEALER_NAME} wins. -${effective_bet}   Bankroll: ${bankroll}")
                    log(f"  {self.DEALER_NAME}: {random.choice(['House wins.', 'Better luck.', 'Again?'])}")
                else:
                    log(f"  Push. Bankroll: ${bankroll}")
                    log(f"  {self.DEALER_NAME}: We're even. Good for nobody.")

                self.settings.set_blackjack_bankroll(bankroll)

                resp = ask("  Play again? (yes / no)").strip().lower()
                if resp not in ("yes", "y"):
                    break
                log("")

        except Exception as e:
            log(f"  Game interrupted: {e}")

        log(f"  Final bankroll: ${bankroll}")
        log("")
        self._jack_running = False

    @staticmethod
    def _new_deck() -> list:
        suits = ['♠', '♣', '♥', '♦']
        ranks = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']
        deck = [(r, s) for s in suits for r in ranks]
        random.shuffle(deck)
        return deck

    @staticmethod
    def _card_value(rank: str) -> int:
        if rank in ('J', 'Q', 'K'):
            return 10
        if rank == 'A':
            return 11
        return int(rank)

    @classmethod
    def _hand_total(cls, hand: list) -> int:
        total = 0
        aces = 0
        for rank, suit in hand:
            v = cls._card_value(rank)
            if rank == 'A':
                aces += 1
            total += v
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    @staticmethod
    def _is_soft_17(hand: list) -> bool:
        """True if hand is exactly soft 17 (contains an Ace counted as 11)."""
        total = 0
        aces = 0
        for rank, suit in hand:
            if rank == 'A':
                aces += 1
                total += 11
            elif rank in ('J', 'Q', 'K'):
                total += 10
            else:
                total += int(rank)
        # Check if reducing one ace brings us to 17
        return total == 17 and aces > 0

    @staticmethod
    def _hand_str(hand: list, hide_second: bool = False) -> str:
        parts = []
        for i, (rank, suit) in enumerate(hand):
            if hide_second and i == 1:
                parts.append("[??]")
            else:
                parts.append(f"[{rank}{suit}]")
        return "  ".join(parts)

    # ------------------------------------------------------------------ #
    #  /compliment
    # ------------------------------------------------------------------ #

    def _cmd_compliment(self, args: str):
        self.console.append_game(self._compliments.get_line())

    # ------------------------------------------------------------------ #
    #  /roast
    # ------------------------------------------------------------------ #

    def _cmd_roast(self, args: str):
        self.console.append_game(self._roasts.get_line())

    # ------------------------------------------------------------------ #
    #  /haiku
    # ------------------------------------------------------------------ #

    def _cmd_haiku(self, args: str):
        haiku = generate_haiku()
        for line in haiku.split("\n"):
            self.console.append_game(f"  {line}")

    # ------------------------------------------------------------------ #
    #  /moth
    # ------------------------------------------------------------------ #

    def _cmd_moth(self, args: str):
        from techdeck.ui.widgets.moth_widget import MothWidget

        if self.main_window is None:
            self.console.append_system("No window available for moth.")
            return

        # Build target list once
        if not self._moth_targets:
            targets = []
            mw = self.main_window
            if hasattr(mw, 'btn_run') and mw.btn_run.isVisible():
                targets.append(mw.btn_run)
            if hasattr(mw, 'console') and mw.console.send_btn.isVisible():
                targets.append(mw.console.send_btn)
            if hasattr(mw, 'console') and mw.console.clear_btn.isVisible():
                targets.append(mw.console.clear_btn)
            if not targets:
                self.console.append_system("Nothing to land on.")
                return
            self._moth_targets = targets

        target = self._moth_targets[self._moth_target_idx % len(self._moth_targets)]
        self._moth_target_idx += 1

        if self._moth is None or not self._moth.isVisible():
            from PySide6.QtGui import QColor
            theme = self.settings.get_theme()
            moth_color = QColor(240, 240, 240, 230) if theme == "dark" else QColor(20, 20, 20, 230)
            self._moth = MothWidget(color=moth_color)
            self._moth.spawn_from_edge(target)
            self.console.append_system("Something has arrived.")
        else:
            self._moth.fly_to(target)
            self.console.append_system("Shoo.")
