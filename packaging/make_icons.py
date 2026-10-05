"""Generate app icons (.png, .ico, .icns) into packaging/assets/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from remindersys.icon import draw_icon  # noqa: E402

out = Path(__file__).resolve().parent / "assets"
out.mkdir(exist_ok=True)
big = draw_icon(1024)
big.save(out / "icon.png")
big.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
big.save(out / "icon.icns")
print(f"Icons written to {out}")
