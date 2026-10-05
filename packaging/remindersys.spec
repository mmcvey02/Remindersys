# PyInstaller spec - builds RemindersSys.exe (Windows) or RemindersSys.app (macOS).
#   pyinstaller --noconfirm packaging/remindersys.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

sys.path.insert(0, str(Path(SPECPATH).parent))
from remindersys import __version__  # noqa: E402

ROOT = Path(SPECPATH).parent
ASSETS = Path(SPECPATH) / "assets"

hiddenimports = collect_submodules("remindersys") + collect_submodules("caldav")
hiddenimports += ["keyring.backends"]
if sys.platform == "win32":
    hiddenimports += ["pystray._win32", "keyring.backends.Windows"]
elif sys.platform == "darwin":
    hiddenimports += ["pystray._darwin", "keyring.backends.macOS", "EventKit", "Foundation", "AppKit"]

a = Analysis(
    [str(Path(SPECPATH) / "entry.py")],
    pathex=[str(ROOT)],
    hiddenimports=hiddenimports,
    datas=collect_data_files("caldav") + collect_data_files("tzdata"),
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="RemindersSys",
        console=False,
        argv_emulation=False,
        icon=str(ASSETS / "icon.icns"),
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="RemindersSys")
    app = BUNDLE(
        coll,
        name="RemindersSys.app",
        icon=str(ASSETS / "icon.icns"),
        bundle_identifier="com.remindersys.app",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            # Menu bar app: no Dock icon.
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSCalendarsUsageDescription":
                "RemindersSys reads your calendar to warn you when it's time to leave for events.",
            "NSCalendarsFullAccessUsageDescription":
                "RemindersSys reads your calendar to warn you when it's time to leave for events.",
            "NSRemindersUsageDescription":
                "RemindersSys reads your reminders to build daily and weekly summaries.",
            "NSRemindersFullAccessUsageDescription":
                "RemindersSys reads your reminders to build daily and weekly summaries.",
            "NSAppleEventsUsageDescription":
                "RemindersSys uses AppleScript to show notifications.",
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="RemindersSys",
        console=False,
        upx=False,
        icon=str(ASSETS / "icon.ico"),
        version=str(Path(SPECPATH) / "version_info.txt") if sys.platform == "win32" else None,
    )
