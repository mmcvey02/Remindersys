"""Command-line entry point.

    RemindersSys                 start in the tray (same as "run")
    RemindersSys run [--headless]
    RemindersSys setup           open the settings window
    RemindersSys sync            print items, priorities and planned alerts
    RemindersSys summary daily|weekly [--no-browser]
    RemindersSys autostart enable|disable|status
    RemindersSys --demo ...      use generated sample data
"""

from __future__ import annotations

import argparse
import logging
import socket
import subprocess
import sys
from logging.handlers import RotatingFileHandler

from remindersys import __version__, autostart
from remindersys.config import Config, data_dir

log = logging.getLogger("remindersys")

SINGLE_INSTANCE_PORT = 47613


def setup_logging(verbose: bool) -> None:
    handlers: list[logging.Handler] = [
        RotatingFileHandler(data_dir() / "remindersys.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    ]
    if sys.stderr is not None:  # windowed builds have no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def out(text: str = "") -> None:
    if sys.stdout is not None:
        print(text)


def _attach_windows_console() -> None:
    """The .exe is a GUI app with no console; when run from a terminal with a
    command, attach to that terminal so output is visible."""
    import ctypes

    if ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
        sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
        sys.stderr = sys.stdout


def acquire_single_instance() -> socket.socket | None:
    """Hold a localhost port for the process lifetime so only one copy runs."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        sock.listen(1)
        return sock
    except OSError:
        sock.close()
        return None


def build_app(args):
    from remindersys.app import App
    from remindersys.notifier import Notifier
    from remindersys.state import State

    config = Config.load()
    if args.demo:
        config.source = "demo"
    return App(config, State(), Notifier(config.modal_alert_for_critical))


def cmd_run(args) -> int:
    from remindersys.sources import needs_setup
    from remindersys.state import State

    lock = acquire_single_instance()
    if lock is None:
        log.info("Another instance is already running")
        out("RemindersSys is already running.")
        return 0

    config = Config.load()
    state = State()
    if not state.first_run_done and not args.headless:
        if not args.demo and (not Config.exists() or needs_setup(config)):
            # Separate process: Tk and the tray both want to own the macOS main loop.
            subprocess.run(autostart.launch_command()[:-1] + ["setup"])
            config = Config.load()
        # Only the packaged app registers itself; running from source shouldn't.
        if getattr(sys, "frozen", False) and config.start_at_login and not autostart.is_enabled():
            try:
                autostart.enable()
            except Exception as exc:  # noqa: BLE001
                log.error("Could not enable start at login: %s", exc)
        state.first_run_done = True
        state.save()

    app = build_app(args)
    log.info("RemindersSys %s starting (source=%s)", __version__, app.config.source)
    if not args.headless:
        try:
            from remindersys.tray import run_tray

            run_tray(app)
            return 0
        except Exception as exc:  # noqa: BLE001 - e.g. no display / tray support
            log.warning("Tray unavailable (%s); running headless", exc)
    try:
        app.run_forever()
    except KeyboardInterrupt:
        app.stop()
    return 0


def cmd_setup(args) -> int:
    from remindersys.setup_ui import run_setup

    try:
        run_setup()
    except Exception as exc:  # noqa: BLE001 - e.g. Tk unavailable
        log.error("Settings window unavailable: %s", exc)
        out(f"Settings window unavailable ({exc}). Edit {Config.path()} instead.")
        if not Config.exists():
            Config().save()
        return 1
    return 0


def cmd_sync(args) -> int:
    from remindersys.scheduler import fmt_time

    app = build_app(args)
    if not app.sync():
        out(f"Sync failed: {app.last_error}")
        return 1
    out(f"{len(app.items)} items from {app.source.name}\n")
    for a in sorted(app.items, key=lambda a: (a.item.start is None, a.item.start and a.item.start.timestamp())):
        item = a.item
        when = "undated" if item.start is None else f"{item.start:%a %m-%d} " + (
            "all-day" if item.all_day else fmt_time(item.start)
        )
        travel = ""
        if a.travel and a.travel.needs_travel:
            travel = f" [travel {a.travel.minutes} min via {a.travel.method}]"
        out(f"{a.priority.tier.label:>8} {a.priority.score:>3}  {when:<17} {item.kind.value:<8} {item.title}{travel}")
        if args.verbose and a.priority.reasons:
            out(f"{'':>14}{', '.join(a.priority.reasons)}")
    out("\nPlanned notifications:")
    for n in app.planned:
        out(f"  {n.fire_at:%a %m-%d %H:%M}  [{n.tier.label}] {n.title} — {n.message}")
    return 0


def cmd_summary(args) -> int:
    app = build_app(args)
    if not app.sync():
        out(f"Sync failed: {app.last_error}")
        return 1
    summary = app.build_summary(args.kind)
    out(summary.to_text())
    path = app.deliver_summary(summary, open_browser=not args.no_browser)
    out(f"\nSaved to {path}")
    return 0


def cmd_autostart(args) -> int:
    if args.action == "enable":
        autostart.enable()
    elif args.action == "disable":
        autostart.disable()
    out("Start at login: " + ("enabled" if autostart.is_enabled() else "disabled"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="RemindersSys", description="Smart notifications for Apple Calendar & Reminders")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--demo", action="store_true", help="use generated sample data")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("run", help="run in the background (default)")
    p.add_argument("--headless", action="store_true", help="no tray icon")
    p.set_defaults(func=cmd_run)
    sub.add_parser("setup", help="open the settings window").set_defaults(func=cmd_setup)
    sub.add_parser("sync", help="sync once and print what was found").set_defaults(func=cmd_sync)
    p = sub.add_parser("summary", help="build and show a summary now")
    p.add_argument("kind", choices=["daily", "weekly"])
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_summary)
    p = sub.add_parser("autostart", help="manage start at login")
    p.add_argument("action", choices=["enable", "disable", "status"])
    p.set_defaults(func=cmd_autostart)

    argv = sys.argv[1:] if argv is None else argv
    if argv and sys.platform == "win32" and sys.stdout is None:
        _attach_windows_console()
    # Old macOS versions pass a "-psn_..." process serial number to apps opened from Finder.
    args = parser.parse_args([a for a in argv if not a.startswith("-psn")])
    setup_logging(args.verbose)
    if args.command is None:
        args.func, args.headless = cmd_run, False
    return args.func(args)
