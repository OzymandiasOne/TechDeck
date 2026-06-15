"""
TechDeck Command Handler
Processes console commands and returns responses.
"""

import random
import sys
import threading
from typing import Callable
from pathlib import Path
from techdeck.core.settings import SettingsManager
from techdeck.core.constants import APP_VERSION
from techdeck.core.flavor import generate_haiku, generate_musing
from techdeck.core.audio_manager import (
    get_audio_manager, SOUND_CARD_DEAL, SOUND_CARD_DEALER_FINAL, SOUND_RAVE_MUSIC,
)
# _rave_player and _rave_audio_out are stored as instance attrs to prevent GC during playback


def _images_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "images"
    return Path(__file__).resolve().parents[2] / "assets" / "images"


class CommandHandler:
    """
    Handles console commands.

    Commands:
        /help           - Show available commands
        /clear          - Clear console
        /version        - Show TechDeck version
        /dash           - Reopen the Dashboard tab
        /fidget         - Open fidget spinner window
        /rave           - Pulse accent colors through a rainbow
        /jack           - Play blackjack in the console
        /roguemode      - Open Rogue Mode focus music player
        /friend         - Summon a little friend (moth/butterfly) with haiku + musings
        /steelbeams     - Open the Steel Tube Operation game

    Theme switching is handled via Settings → Personalization → Theme,
    not the console. Kit/tile/guide commands have been retired in
    favor of the visual surfaces (Home, Library, and the Help &
    Feedback tab).
    """

    def __init__(self, settings: SettingsManager, console_widget, main_window=None):
        self.settings = settings
        self.console = console_widget
        self.main_window = main_window

        # Runtime state
        self._steelbeams_window = None
        self._rave_timer = None
        self._rave_step = 0
        self._rave_gifs = []     # list of QWidget overlay windows
        self._rave_movie = None  # single shared QMovie — decoded once, drives all labels
        self._rave_player = None
        self._rave_audio_out = None
        self._rave_theme_name = None     # theme to restore when the rave ends
        self._rave_orig = None           # (accent, hover, pressed) saved before raving
        self._crabs = []
        self._moths = []  # every /friend adds one (capped), /clear shoos them all
        self._jack_running = False
        self._jack_cancel = threading.Event()  # set to fold/abort an active game

        self._rogue_player = None  # kept alive here to prevent GC
        self._spinner = None       # /fidget window; /clear closes it

        # Command registry. Theme switching deliberately is NOT here —
        # the only way to change theme is via Settings → Personalization
        # so the console doesn't compete with the live preview path.
        # Kit/tile/guide listing has been retired too; those surfaces
        # belong to Home, Library, and the Help & Feedback tab.
        self.commands = {
            '/help': self._cmd_help,
            '/clear': self._cmd_clear,
            '/version': self._cmd_version,
            '/info': self._cmd_info,
            '/dash': self._cmd_dash,
            '/pause': self._cmd_pause,
            '/resume': self._cmd_resume,
            '/shelve': self._cmd_shelve,
            '/fidget': self._cmd_fidget,
            '/rave': self._cmd_rave,
            '/steelbeams': self._cmd_steelbeams,
            '/jack': self._cmd_jack,
            '/roguemode': self._cmd_roguemode,
            '/friend': self._cmd_moth,
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
        help_text = (
            "Available commands:\n"
            "\n"
            "  /help            - Show this help message\n"
            "  /clear           - Clear console output\n"
            "  /version         - Show TechDeck version\n"
            "  /info            - Describe the selected tile(s)\n"
            "  /dash            - Reopen the Dashboard tab\n"
            "  /pause           - Pause the current run at its input prompt\n"
            "  /resume          - Resume a paused run (or load the shelved one)\n"
            "  /shelve          - Save the rest of the run to disk for later\n"
            "  /shelve view     - Show what's currently on the shelf\n"
            "  /shelve clear    - Drop the shelf entry\n"
            "  /roguemode       - Open Rogue Mode focus music player\n"
            "\n"
            "  /fidget          - Pop out a fidget spinner\n"
            "  /steelbeams      - Launch Steel Tube Operation\n"
            "  /jack            - Play blackjack against Sal\n"
            "  /friend          - Summon a little friend\n"
            "\n"
            "  Theme switching lives in Settings → Personalization → Theme.\n"
            "  Kits, apps, and docs live in the Home and Library pages."
        )
        # Record where the appended block will start so we can scroll the
        # viewport there after appending. The console auto-scrolls to bottom
        # on every append, which lands the user at the END of the help text —
        # disorienting because they want to read from "Available commands:"
        # downward.
        output = getattr(self.console, "output", None)
        pre_pos = output.document().characterCount() - 1 if output is not None else None
        self.console.append_system(help_text)
        if output is not None and pre_pos is not None:
            from PySide6.QtGui import QTextCursor
            anchor = QTextCursor(output.document())
            anchor.setPosition(pre_pos)
            rect = output.cursorRect(anchor)
            sb = output.verticalScrollBar()
            sb.setValue(sb.value() + rect.top())
            # Anchoring at the top hides the rest of the list below the fold —
            # show a floating "read more" pill so that's discoverable.
            if sb.value() < sb.maximum():
                self.console.show_read_more_hint()

    def _cmd_clear(self, args: str):
        self.console.clear()

    def _cmd_version(self, args: str):
        self.console.append_system(f"TechDeck v{APP_VERSION}")

    def _cmd_dash(self, args: str):
        if hasattr(self.console, "reopen_dashboard"):
            self.console.reopen_dashboard()
            self.console.append_system("Dashboard reopened.")
        else:
            self.console.append_error("Dashboard not available.")

    def _cmd_pause(self, args: str):
        """Pause the current multi-plugin run at its active input prompt."""
        home = self._home_page()
        if home is None:
            self.console.append_error("Home page not available.")
            return
        home.pause_run(source="user")

    def _cmd_resume(self, args: str):
        """Resume a paused run from the parked plugin, or load a shelved run."""
        home = self._home_page()
        if home is None:
            self.console.append_error("Home page not available.")
            return
        home.resume_run()

    def _cmd_shelve(self, args: str):
        """Single-slot shelve. Subcommands:
          /shelve         — save the remaining queue (+ shared state) to disk
          /shelve view    — print the current shelf
          /shelve clear   — drop the shelf entry
        """
        home = self._home_page()
        if home is None:
            self.console.append_error("Home page not available.")
            return
        sub = args.strip().lower()
        if sub == "":
            home.shelve_run()
        elif sub == "view":
            home.view_shelf()
        elif sub == "clear":
            home.clear_shelf()
        else:
            self.console.append_error(
                f"Unknown /shelve subcommand: '{sub}'. "
                f"Use /shelve, /shelve view, or /shelve clear."
            )

    def _home_page(self):
        """Return the HomePage instance, or None if unreachable."""
        mw = self.main_window
        if mw is None or not hasattr(mw, "home_page"):
            return None
        return mw.home_page

    def _cmd_info(self, args: str):
        """Print descriptions for every currently selected tile on Home.

        Replaces the previous tile-tooltip workflow — tooltips would
        get cut off for long descriptions. Select the apps you want
        details on, then run /info.
        """
        mw = self.main_window
        if mw is None or not hasattr(mw, "home_page"):
            self.console.append_error("Home page not available.")
            return
        home = mw.home_page
        selected = sorted(home.selected_tiles)
        if not selected:
            self.console.append_system(
                "No apps selected. Click one or more tiles on Home, then run /info."
            )
            return
        lines = []
        for tile_id in selected:
            plugin = home.plugin_loader.get_plugin(tile_id)
            if plugin is None:
                lines.append(f"{tile_id} — (plugin not installed)")
                continue
            description = (plugin.description or "(no description)").strip()
            lines.append(f"{plugin.name}")
            lines.append(f"  {description}")
            lines.append("")
        # Drop trailing blank line for cleanliness
        while lines and lines[-1] == "":
            lines.pop()
        self.console.append_system("\n".join(lines))

    # ------------------------------------------------------------------ #
    #  /fidget
    # ------------------------------------------------------------------ #

    def _cmd_fidget(self, args: str):
        from techdeck.ui.widgets.fidget_spinner import FidgetSpinnerWindow
        # Only ever one spinner — re-running /fidget replaces it.
        self._stop_spinner()
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
        self.console.append_system("Give it a spin. Type /clear to put it away.")

    # ------------------------------------------------------------------ #
    #  /rave
    # ------------------------------------------------------------------ #

    _RAVE_COLORS = [
        "#FF2080", "#FF8000", "#FFE000", "#00E060",
        "#00CFFF", "#5050FF", "#CC00FF", "#FF2080",
    ]

    _FLOWER_FRAMES = ["✿", "❀", "✾", "✼", "❁", "✻", "✺", "✹", "✸", "✷"]

    def _rave_spinner_html(self, flower: str, color: str) -> str:
        return (
            f'<span style="color: {color}; font-weight: bold; '
            f'font-family: Consolas, monospace; font-size: 10pt;">'
            f'{flower}&nbsp;&nbsp;Crab Dancing...</span>'
        )

    # ------------------------------------------------------------------ #
    #  /steelbeams
    # ------------------------------------------------------------------ #

    def _cmd_steelbeams(self, args: str):
        from techdeck.ui.widgets.steelbeams_game import SteelBeamsGame
        if self._steelbeams_window is not None and self._steelbeams_window.isVisible():
            self._steelbeams_window.raise_()
            self._steelbeams_window.activateWindow()
            return
        self._steelbeams_window = SteelBeamsGame()
        self._steelbeams_window.show()

    def _cmd_rave(self, args: str):
        from PySide6.QtWidgets import QApplication, QLabel, QWidget
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtGui import QMovie
        from techdeck.ui.theme import THEMES, generate_stylesheet
        from techdeck.ui.widgets.crab_widget import CrabWidget

        if self._rave_timer is not None:
            self.console.append_system("Already raving.")
            return

        app = QApplication.instance()
        if app is None:
            return

        theme_name = self.settings.get_theme()
        if theme_name not in THEMES:
            theme_name = "dark"

        # Save originals (stored on self so _stop_rave can restore on /clear too)
        orig_accent = THEMES[theme_name].accent
        orig_hover = THEMES[theme_name].accent_hover
        orig_pressed = THEMES[theme_name].accent_pressed
        self._rave_theme_name = theme_name
        self._rave_orig = (orig_accent, orig_hover, orig_pressed)

        elapsed = [0]
        step = [0]

        # Determine which screen TechDeck is currently on
        target_screen = None
        if self.main_window is not None:
            from PySide6.QtGui import QGuiApplication
            target_screen = QGuiApplication.screenAt(
                self.main_window.geometry().center()
            )
        if target_screen is None:
            target_screen = QApplication.primaryScreen()

        # Spawn 5 crabs on the same screen as TechDeck
        self._crabs = []
        for _ in range(5):
            crab = CrabWidget()
            crab.start(target_screen)
            self._crabs.append(crab)

        # Spawn 4 cat GIF overlays sharing one QMovie — decoded once, all labels update together
        self._rave_gifs = []
        self._rave_movie = None
        gif_path = _images_dir() / "cat.gif"
        if gif_path.exists():
            screen_geo = target_screen.geometry()
            from PySide6.QtGui import QImageReader
            from PySide6.QtCore import QSize, QRect
            reader = QImageReader(str(gif_path))
            natural = reader.size()
            fw = int(natural.width() * 0.75) if natural.width() > 0 else 100
            fh = int(natural.height() * 0.75) if natural.height() > 0 else 100
            movie = QMovie(str(gif_path))
            movie.setScaledSize(QSize(fw, fh))
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            movie.start()
            self._rave_movie = movie
            x_min = screen_geo.left()
            x_max = max(screen_geo.left(), screen_geo.right() - fw)
            y_min = screen_geo.top()
            y_max = max(screen_geo.top(), screen_geo.bottom() - fh)
            placed = []
            for _ in range(4):
                # Try up to 100 random positions; take the first non-overlapping one
                x, y = random.randint(x_min, x_max), random.randint(y_min, y_max)
                for _ in range(100):
                    cx, cy = random.randint(x_min, x_max), random.randint(y_min, y_max)
                    candidate = QRect(cx, cy, fw, fh)
                    if not any(candidate.intersects(r) for r in placed):
                        x, y = cx, cy
                        break
                placed.append(QRect(x, y, fw, fh))
                gif_w = QWidget(
                    None,
                    Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.Tool
                    | Qt.WindowType.WindowStaysOnTopHint,
                )
                gif_w.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                lbl = QLabel(gif_w)
                lbl.setMovie(movie)  # all labels share the same movie instance
                lbl.resize(fw, fh)
                gif_w.resize(fw, fh)
                gif_w.move(x, y)
                gif_w.show()
                self._rave_gifs.append(gif_w)

        # Start rave music via QMediaPlayer (buffered — no skipping on longer files)
        result = get_audio_manager().play_music_stoppable(SOUND_RAVE_MUSIC)
        if result:
            self._rave_player, self._rave_audio_out = result
        else:
            self._rave_player = self._rave_audio_out = None

        # Show spinner label and kick off rave
        self.console.append_game("Let's rave.")
        self.console.show_spinner(
            self._rave_spinner_html(self._FLOWER_FRAMES[0], self._RAVE_COLORS[0])
        )

        def tick():
            elapsed[0] += 400
            if elapsed[0] >= 10_000:
                self._stop_rave()
                return

            color = self._RAVE_COLORS[step[0] % len(self._RAVE_COLORS)]
            flower = self._FLOWER_FRAMES[step[0] % len(self._FLOWER_FRAMES)]
            step[0] += 1
            THEMES[theme_name].accent = color
            THEMES[theme_name].accent_hover = color
            THEMES[theme_name].accent_pressed = color
            app.setStyleSheet(generate_stylesheet(theme_name))
            # Update spinner label
            self.console.update_spinner(self._rave_spinner_html(flower, color))

        self._rave_timer = QTimer()
        self._rave_timer.setInterval(400)
        self._rave_timer.timeout.connect(tick)
        self._rave_timer.start()

    # ------------------------------------------------------------------ #
    #  Session teardown — invoked by /clear and the Clear button
    # ------------------------------------------------------------------ #

    def stop_session_effects(self):
        """End easter-egg sessions on /clear or the Clear button: fold blackjack,
        end /rave, dismiss /friend, and put the fidget spinner away. The Steel
        Beams game is a separate window, left to be closed manually."""
        self._stop_jack()
        self._stop_rave(announce=False)
        self._stop_moth()
        self._stop_spinner()

    def _stop_spinner(self):
        """Close the /fidget spinner window if one is open (used by /clear)."""
        if self._spinner is not None:
            try:
                self._spinner.close()
            except Exception:
                pass
            self._spinner = None

    def _stop_jack(self):
        """Fold an in-progress blackjack hand and end the game."""
        if self._jack_running:
            self._jack_cancel.set()
            self.console.abort_input()  # unblock the game thread if it's waiting

    def _stop_rave(self, announce: bool = True):
        """Tear down the rave: restore the theme, stop crabs/music/GIFs, hide the
        spinner. Safe to call when no rave is active. `announce` logs the finale
        line (used by the natural timeout, suppressed on /clear)."""
        if self._rave_timer is None:
            return
        from PySide6.QtWidgets import QApplication
        from techdeck.ui.theme import THEMES, generate_stylesheet

        app = QApplication.instance()
        if self._rave_theme_name in THEMES and self._rave_orig is not None:
            accent, hover, pressed = self._rave_orig
            THEMES[self._rave_theme_name].accent = accent
            THEMES[self._rave_theme_name].accent_hover = hover
            THEMES[self._rave_theme_name].accent_pressed = pressed
            if app is not None:
                app.setStyleSheet(generate_stylesheet(self._rave_theme_name))

        self._rave_timer.stop()
        self._rave_timer = None
        for crab in self._crabs:
            crab.stop()
        self._crabs = []
        if self._rave_player is not None:
            self._rave_player.stop()
            self._rave_player = None
            self._rave_audio_out = None
        if self._rave_movie is not None:
            self._rave_movie.stop()
            self._rave_movie = None
        for gif_w in self._rave_gifs:
            gif_w.close()
        self._rave_gifs = []
        self.console.hide_spinner()
        if announce:
            self.console.append_system("Rave over. Productivity +10.")

    def _stop_moth(self):
        """Dismiss all moths if present (used by /clear)."""
        for moth in self._moths:
            try:
                moth.dismiss()
            except Exception:
                pass
        self._moths = []

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
        self._jack_cancel.clear()
        t = threading.Thread(target=self._jack_game_loop, daemon=True, name="BlackjackGame")
        t.start()

    def _jack_game_loop(self):
        from techdeck.ui.widgets.console import InputAborted

        log = self.console.safe_game_log

        def ask(prompt):
            # Marked owner='game' so a slash command folds the hand instead of
            # being eaten as a move. _jack_cancel covers the gap between prompts.
            if self._jack_cancel.is_set():
                raise InputAborted()
            return self.console.request_input(prompt, owner='game')

        bankroll = self.settings.get_blackjack_bankroll()
        bet = self.JACK_BET

        log("")
        log(f"  -- BLACKJACK with {self.DEALER_NAME} --")
        log(f"  Bankroll: ${bankroll}   You set your bet each hand (starts at ${bet})")
        log(f"  Commands: hit  stand  double  quit")
        log("")

        try:
            while True:
                if bankroll <= 0:
                    log(f"  {self.DEALER_NAME}: You're broke. Here's $100. Don't.")
                    bankroll = 100
                    self.settings.set_blackjack_bankroll(bankroll)

                # --- Bet for this hand ---
                # (The console ignores empty submissions, so "same" repeats
                # the previous bet instead of a bare Enter.)
                bet = min(bet, bankroll)
                while True:
                    raw = ask(f"  Bet? (1-{bankroll}, 'same' = ${bet}, quit)").strip().lower()
                    if raw in ("quit", "q"):
                        log(f"  {self.DEALER_NAME}: Come back when you're ready.")
                        self.settings.set_blackjack_bankroll(bankroll)
                        self._jack_running = False
                        return
                    if raw in ("same", "s"):
                        break
                    try:
                        amount = int(raw.lstrip("$"))
                    except ValueError:
                        log("  A dollar amount, 'same', or 'quit'.")
                        continue
                    if amount < 1:
                        log("  Minimum bet is $1.")
                    elif amount > bankroll:
                        log(f"  You only have ${bankroll}.")
                    else:
                        bet = amount
                        break

                # --- Deal ---
                deck = self._new_deck()
                player = [deck.pop(), deck.pop()]
                dealer = [deck.pop(), deck.pop()]
                get_audio_manager().safe_play(SOUND_CARD_DEAL)

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
                        if player_total == 21:
                            # Nothing left to decide — stand automatically and
                            # let the dealer play out the hand.
                            log(f"  Twenty-one. {self.DEALER_NAME} plays it out.")
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
                get_audio_manager().safe_play(SOUND_CARD_DEALER_FINAL)

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

        except InputAborted:
            # Folded mid-hand because the user ran another command (or cleared).
            self.settings.set_blackjack_bankroll(bankroll)
            self._jack_running = False
            return
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
    #  /roguemode
    # ------------------------------------------------------------------ #

    def _cmd_roguemode(self, args: str):
        from techdeck.ui.widgets.rogue_mode_player import RogueModePlayer
        is_first_open = RogueModePlayer._instance is None
        parent = self.main_window if self.main_window is not None else None
        self._rogue_player = RogueModePlayer.get_or_create(self.settings, parent=parent)
        if is_first_open:
            self.console.append_game("Rogue Mode activated. Lock in.")
            self.console.append_system("Tech Tip: Add music and build playlists in the settings tab!")
        else:
            self.console.append_system("Rogue Mode player open.")

    # ------------------------------------------------------------------ #
    #  /friend — moth/butterfly flies to a random empty spot, shows haiku + musings
    # ------------------------------------------------------------------ #

    def _cmd_moth(self, args: str):
        from techdeck.ui.widgets.moth_widget import (
            MothWidget, MOTH_FRAMES, BUTTERFLY_FRAMES)
        from techdeck.ui.theme_manager import get_theme_manager
        from PySide6.QtGui import QColor
        from PySide6.QtCore import QPoint

        mw = self.main_window
        if mw is None:
            self.console.append_system("No window available.")
            return

        # A random point in the upper-central content area of the window — chosen
        # to avoid the button bars (Run, console Send/Clear) so it never lands on
        # a button.
        tl = mw.mapToGlobal(QPoint(0, 0))
        w, h = mw.width(), mw.height()
        point = QPoint(
            tl.x() + random.randint(int(w * 0.22), int(w * 0.78)),
            tl.y() + random.randint(int(h * 0.18), int(h * 0.50)),
        )

        # Colour the moth + haiku bubble to the active theme. The moth holds the
        # haiku generator and shows one ~30s after landing, then every ~10 min.
        tm = get_theme_manager()
        pal = tm.get_current_palette()
        # Two-tone body + darker outline, coloured to the theme accent.
        moth_color = QColor(pal.accent)
        moth_color.setAlpha(235)
        moth_outline = moth_color.darker(260)
        # Cherry theme gets a butterfly instead of a moth.
        is_butterfly = tm.get_current_theme() == "cherry_blossom"
        frames = BUTTERFLY_FRAMES if is_butterfly else MOTH_FRAMES
        critter = "butterfly" if is_butterfly else "moth"
        # bubble: surface fill, accent frame/arrow, and a text colour kept DISTINCT
        # from the frame -- warm cream on a dark fill, warm brown on a light fill
        # (AC-style, readable, and never the same as the accent).
        bg, frame = QColor(pal.surface), QColor(pal.accent)
        lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        fg = QColor("#3A2A14") if lum > 150 else QColor("#F3EAD2")

        # Every /friend invites ANOTHER critter in (click one to send it to a
        # new perch; double-click or /clear to shoo them away). Capped so the
        # office doesn't turn into an aviary.
        self._moths = [m for m in self._moths if m is not None and m.isVisible()]
        if len(self._moths) >= 6:
            self.console.append_system(
                f"Six {critter}s is plenty. The office is not an aviary.")
            return
        moth = MothWidget(color=moth_color, outline=moth_outline, frames=frames)
        moth.configure_speech(generate_haiku, generate_musing, fg, bg, frame)
        moth.attach_to(mw)             # follow + minimize with the window
        moth.spawn_from_edge(point)
        self._moths.append(moth)
        if len(self._moths) == 1:
            self.console.append_system(f"A {critter} flutters in and settles down.")
        else:
            self.console.append_system(f"Another {critter} flutters in to join the first.")
