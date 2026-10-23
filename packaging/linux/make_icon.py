"""Make the Linux menu icon: the logo centred on a square, transparent canvas.

    python packaging/linux/make_icon.py <out.png> [size]

Media/morkyn-logo.png is taller than wide; a plain resize would squash it.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    out = Path(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    logo = Image.open(ROOT / "Media" / "morkyn-logo.png").convert("RGBA")
    side = max(logo.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    square.resize((size, size), Image.LANCZOS).save(out)


if __name__ == "__main__":
    main()
