"""Write the Windows version resource consumed by the PyInstaller spec."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from remindersys import __version__  # noqa: E402

parts = (__version__.split(".") + ["0", "0", "0"])[:4]
nums = ", ".join(str(int(p)) for p in parts)
template = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums})),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'RemindersSys'),
      StringStruct('FileDescription', 'RemindersSys - smart calendar and reminder notifications'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('ProductName', 'RemindersSys'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('OriginalFilename', 'RemindersSys.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
(Path(__file__).resolve().parent / "version_info.txt").write_text(template, encoding="utf-8")
