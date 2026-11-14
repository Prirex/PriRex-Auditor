"""Генерирует PNG-логотип и .ico из assets/logo.svg.

Запуск:  python tools/make_assets.py
Утилита одноразовая, но лежит в репозитории, чтобы иконку можно было
пересобрать при смене логотипа. Нужны PySide6 (QtSvg) и Pillow.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

#: Квадратный холст для иконки приложения (px).
ICON_CANVAS = 512
#: Отступ логотипа от края квадратной иконки.
ICON_MARGIN_RATIO = 0.12


def to_pil(image: QImage) -> Image.Image:
    image = image.convertToFormat(QImage.Format_ARGB32)
    width, height = image.width(), image.height()
    data = bytes(image.constBits())
    return Image.frombuffer(
        "RGBA", (width, height), data, "raw", "BGRA", image.bytesPerLine(), 1
    )


def render_svg(svg: QSvgRenderer, width: int, height: int) -> Image.Image:
    image = QImage(QSize(width, height), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
    )
    svg.render(painter)
    painter.end()
    return to_pil(image)


def trim_transparent(image: Image.Image, padding: int = 4) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return image
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def square_icon(logo: Image.Image, canvas: int = ICON_CANVAS) -> Image.Image:
    """Логотип на прозрачном квадратном холсте с отступом, без растягивания."""
    margin = int(canvas * ICON_MARGIN_RATIO)
    available = canvas - margin * 2
    scale = min(available / logo.width, available / logo.height)
    width = max(1, int(logo.width * scale))
    height = max(1, int(logo.height * scale))
    resized = logo.resize((width, height), Image.LANCZOS)
    icon = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    icon.paste(resized, ((canvas - width) // 2, (canvas - height) // 2), resized)
    return icon


def main() -> int:
    svg_path = ASSETS / "logo.svg"
    if not svg_path.exists():
        print(f"Не найден {svg_path}", file=sys.stderr)
        return 1

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        print("Не удалось прочитать SVG-логотип", file=sys.stderr)
        return 1

    # 1. Логотип в высоком разрешении: 1024 px по широкой стороне.
    base = render_svg(renderer, 1024, 600)
    logo = trim_transparent(base, padding=6)
    logo.save(ASSETS / "logo.png", optimize=True)
    print(f"logo.png: {logo.width}x{logo.height}")

    # 2. Квадратная иконка приложения и .ico для Windows.
    icon = square_icon(logo)
    icon.save(ASSETS / "icon.png", optimize=True)
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(ASSETS / "logo.ico", sizes=ico_sizes)
    print(f"logo.ico: {ICON_CANVAS}x{ICON_CANVAS} ({len(ico_sizes)} размеров)")

    # 3. Уменьшенный логотип для заголовка окна/футера (высота 28 px @2x).
    header = logo.resize((max(1, int(logo.width * 56 / logo.height)), 56), Image.LANCZOS)
    header.save(ASSETS / "logo_header.png", optimize=True)
    print(f"logo_header.png: {header.width}x{header.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
