#!/usr/bin/env python3
"""Generate the Windows executable icon from a project image.

The source image is ``docs/images/blacksmith.jpeg``. The generated icon is
``build/blacksmith.ico`` with sizes from 16x16 up to 256x256. The image is
center-cropped to a square first so Windows does not stretch or letterbox it.

Used by ``CurveTracer.spec`` (all PyInstaller builds, including GitHub Actions)
and by ``build_windows.bat``. Replace the JPEG to change the application icon.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - build-time only
    print(
        "ERROR: Pillow is required to generate the icon. "
        "Install requirements-build.txt.",
        file=sys.stderr,
    )
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "images" / "blacksmith.jpeg"
OUTPUT = ROOT / "build" / "blacksmith.ico"

SIZES = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]


def main() -> int:
    if not SOURCE.exists():
        print(f"ERROR: icon source not found: {SOURCE}", file=sys.stderr)
        return 1

    image = Image.open(SOURCE).convert("RGBA")

    # Center-crop to a square, then resize to the largest icon size.
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((256, 256), Image.Resampling.LANCZOS)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, format="ICO", sizes=SIZES)
    print(f"[icon] generated {OUTPUT} from {SOURCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
