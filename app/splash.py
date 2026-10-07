"""Ladebildschirm beim Programmstart.

In der Mitte steht das Schullogo, darunter die Urheberzeile, in der Ecke
die Version. Das Bild wird einmal gezeichnet und als ``QSplashScreen``
gezeigt, bis das Hauptfenster bereit ist.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from app import config, icons, resources

LOGO_FILE = "bs_technik_logo.png"
SPLASH_WIDTH = 560
SPLASH_HEIGHT = 440
# Das Logo hat einen schwarzen Rand – auf Schwarz fügt es sich nahtlos ein
BACKGROUND = "#000000"
TEXT_COLOR = "#f2f2f2"
MUTED_COLOR = "#8c8c8c"


def version_text() -> str:
    return f"Version {config.APP_VERSION}"


def load_logo() -> QPixmap:
    """Das Schullogo; fehlt die Datei, ersatzweise das Programmsymbol."""
    logo = QPixmap(resources.asset_path(LOGO_FILE))
    return logo if not logo.isNull() else icons.render_app_icon(200)


def render_splash(device_pixel_ratio: float = 1.0, message: str = "") -> QPixmap:
    """Zeichnet den Ladebildschirm (``message``: zusätzliche Zeile, z. B. beim Aktualisieren)."""
    ratio = max(1.0, float(device_pixel_ratio))
    pixmap = QPixmap(int(SPLASH_WIDTH * ratio), int(SPLASH_HEIGHT * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QColor(BACKGROUND))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    # Logo in der Mitte (etwas oberhalb, damit die Zeile darunter Platz hat)
    logo = load_logo()
    logo_height = 270.0
    logo_width = logo_height * logo.width() / max(1, logo.height())
    logo_rect = QRectF((SPLASH_WIDTH - logo_width) / 2, 36, logo_width, logo_height)
    painter.drawPixmap(logo_rect, logo, QRectF(logo.rect()))

    font = QFont()
    font.setFamilies(config.ITEM_FONT_FAMILIES)
    font.setPixelSize(15)
    painter.setFont(font)
    painter.setPen(QColor(TEXT_COLOR))
    painter.drawText(QRectF(20, logo_rect.bottom() + 22, SPLASH_WIDTH - 40, 26),
                     Qt.AlignmentFlag.AlignCenter, config.SPLASH_CREDIT)

    font.setPixelSize(12)
    painter.setFont(font)
    painter.setPen(QColor(MUTED_COLOR))
    if message:
        painter.drawText(QRectF(20, logo_rect.bottom() + 54, SPLASH_WIDTH - 40, 22),
                         Qt.AlignmentFlag.AlignCenter, message)
    # Version in der Ecke
    painter.drawText(QRectF(16, SPLASH_HEIGHT - 32, SPLASH_WIDTH - 32, 20),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, version_text())
    painter.end()
    return pixmap


class SplashScreen(QSplashScreen):
    def __init__(self, message: str = ""):
        screen = self.primary_screen_ratio()
        super().__init__(render_splash(screen, message))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    @staticmethod
    def primary_screen_ratio() -> float:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        return screen.devicePixelRatio() if screen is not None else 1.0

    def mousePressEvent(self, event) -> None:
        # Ein Klick soll den Ladebildschirm nicht vorzeitig schließen
        event.ignore()
