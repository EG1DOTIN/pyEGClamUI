"""
Programmatic High-DPI Vector Icon Factory for pyEGClamUI.
Generates razor-sharp, modern, anti-aliased vector icons on-the-fly using PySide6 QPainter.
Zero external asset dependencies, 100% DPI-scaled, and cached in-memory.
"""

from typing import Dict, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)


class IconFactory:
    """Factory creating scalable, anti-aliased vector icons."""

    _cache: Dict[Tuple[str, str, int, float], QIcon] = {}
    _pix_cache: Dict[Tuple[str, str, int, float], QPixmap] = {}

    @classmethod
    def _get_dpr(cls) -> float:
        """Determines the current screen device pixel ratio for High-DPI rendering."""
        try:
            app = QGuiApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    return max(1.0, float(screen.devicePixelRatio()))
        except Exception:
            pass
        return 1.0

    @classmethod
    def get_icon(cls, name: str, color: str = "#ffffff", size: int = 24) -> QIcon:
        """Returns a cached QIcon rendered sharply at the given size and color."""
        dpr = cls._get_dpr()
        key = (name.lower(), color.lower(), size, round(dpr, 2))
        if key not in cls._cache:
            icon = QIcon()
            # Standard 1x pixmap
            pix_1x = cls.get_pixmap(name, color, size, dpr=1.0)
            icon.addPixmap(pix_1x)
            # High-DPI pixmap for crisp rendering on scaled displays
            if dpr > 1.0:
                pix_hd = cls.get_pixmap(name, color, size, dpr=dpr)
                icon.addPixmap(pix_hd)
            else:
                pix_2x = cls.get_pixmap(name, color, size, dpr=2.0)
                icon.addPixmap(pix_2x)
            cls._cache[key] = icon
        return cls._cache[key]

    @classmethod
    def get_pixmap(cls, name: str, color: str = "#ffffff", size: int = 24, dpr: Optional[float] = None) -> QPixmap:
        """Renders and returns a high-DPI anti-aliased vector QPixmap."""
        if dpr is None:
            dpr = cls._get_dpr()

        key = (name.lower(), color.lower(), size, round(dpr, 2))
        if key in cls._pix_cache:
            return cls._pix_cache[key]

        physical_size = int(round(size * dpr))
        pix = QPixmap(physical_size, physical_size)
        pix.fill(Qt.transparent)
        pix.setDevicePixelRatio(dpr)

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        qcolor = QColor(color)
        stroke_w = max(1.4, size * 0.042)
        pen = QPen(qcolor, stroke_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        # Dispatch drawing method based on icon name
        draw_fn = getattr(cls, f"_draw_{name.lower()}", cls._draw_unknown)
        draw_fn(painter, size, qcolor)

        painter.end()
        cls._pix_cache[key] = pix
        return pix

    @classmethod
    def _draw_unknown(cls, p: QPainter, s: int, c: QColor):
        """Fallback circle indicator."""
        m = s * 0.2
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))

    @classmethod
    def _draw_quick_scan(cls, p: QPainter, s: int, c: QColor):
        """Dynamic sharp lightning bolt with crisp polygon vertices."""
        path = QPainterPath()
        path.moveTo(s * 0.52, s * 0.14)
        path.lineTo(s * 0.28, s * 0.52)
        path.lineTo(s * 0.48, s * 0.52)
        path.lineTo(s * 0.40, s * 0.86)
        path.lineTo(s * 0.74, s * 0.44)
        path.lineTo(s * 0.54, s * 0.44)
        path.closeSubpath()

        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawPath(path)
        p.setPen(old_pen)

    _draw_flash = _draw_quick_scan

    @classmethod
    def _draw_full_scan(cls, p: QPainter, s: int, c: QColor):
        """Tiered hard drive / system storage array."""
        m_x = s * 0.20
        w = s * 0.60
        h = s * 0.17

        # 3 stacked drive trays
        for i in range(3):
            y = s * (0.20 + i * 0.23)
            rect = QRectF(m_x, y, w, h)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, s * 0.05, s * 0.05)
            # Drive indicator light (clean solid LED dot)
            old_pen = p.pen()
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(m_x + w * 0.82, y + h * 0.5), s * 0.03, s * 0.03)
            p.setPen(old_pen)

    @classmethod
    def _draw_custom_scan(cls, p: QPainter, s: int, c: QColor):
        """Folder with search magnifying glass."""
        # Folder shape
        folder = QPainterPath()
        folder.moveTo(s * 0.18, s * 0.30)
        folder.lineTo(s * 0.40, s * 0.30)
        folder.lineTo(s * 0.48, s * 0.38)
        folder.lineTo(s * 0.78, s * 0.38)
        folder.lineTo(s * 0.78, s * 0.70)
        folder.lineTo(s * 0.18, s * 0.70)
        folder.closeSubpath()
        p.setBrush(Qt.NoBrush)
        p.drawPath(folder)

        # Magnifying glass on bottom right
        center = QPointF(s * 0.58, s * 0.54)
        radius = s * 0.15
        p.drawEllipse(center, radius, radius)
        # Handle
        p.drawLine(QPointF(s * 0.68, s * 0.64), QPointF(s * 0.80, s * 0.76))

    @classmethod
    def _draw_memory_scan(cls, p: QPainter, s: int, c: QColor):
        """Microprocessor RAM chip with connector pins."""
        # Chip body
        rect = QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, s * 0.06, s * 0.06)

        # Pins on 4 sides
        pin_len = s * 0.11
        for offset in [0.38, 0.50, 0.62]:
            # Top & Bottom
            p.drawLine(QPointF(s * offset, s * 0.28), QPointF(s * offset, s * 0.28 - pin_len))
            p.drawLine(QPointF(s * offset, s * 0.72), QPointF(s * offset, s * 0.72 + pin_len))
            # Left & Right
            p.drawLine(QPointF(s * 0.28, s * offset), QPointF(s * 0.28 - pin_len, s * offset))
            p.drawLine(QPointF(s * 0.72, s * offset), QPointF(s * 0.72 + pin_len, s * offset))

        # Core dot (clean solid core indicator)
        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.05, s * 0.05)
        p.setPen(old_pen)

    @classmethod
    def _draw_refresh(cls, p: QPainter, s: int, c: QColor):
        """Two circular refresh arrows."""
        radius = s * 0.28
        center = QPointF(s * 0.5, s * 0.5)
        rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

        # Draw two arcs
        p.setBrush(Qt.NoBrush)
        p.drawArc(rect, int(35 * 16), int(135 * 16))
        p.drawArc(rect, int(215 * 16), int(135 * 16))

        # Arrowheads (draw with NoPen for crisp triangles)
        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        # Top arrowhead
        top_arrow = QPolygonF([
            QPointF(s * 0.66, s * 0.24),
            QPointF(s * 0.80, s * 0.30),
            QPointF(s * 0.72, s * 0.42),
        ])
        p.drawPolygon(top_arrow)

        # Bottom arrowhead
        bot_arrow = QPolygonF([
            QPointF(s * 0.34, s * 0.76),
            QPointF(s * 0.20, s * 0.70),
            QPointF(s * 0.28, s * 0.58),
        ])
        p.drawPolygon(bot_arrow)
        p.setPen(old_pen)

    @classmethod
    def _draw_restore(cls, p: QPainter, s: int, c: QColor):
        """Curved recovery / undo arrow."""
        path = QPainterPath()
        path.moveTo(s * 0.70, s * 0.68)
        path.cubicTo(s * 0.70, s * 0.42, s * 0.55, s * 0.34, s * 0.34, s * 0.36)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Arrowhead pointing left
        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        arrow = QPolygonF([
            QPointF(s * 0.36, s * 0.22),
            QPointF(s * 0.18, s * 0.36),
            QPointF(s * 0.36, s * 0.50),
        ])
        p.drawPolygon(arrow)
        p.setPen(old_pen)

    @classmethod
    def _draw_delete(cls, p: QPainter, s: int, c: QColor):
        """Modern trashcan with lid and vertical ribs."""
        p.setBrush(Qt.NoBrush)
        # Lid handle
        p.drawArc(QRectF(s * 0.42, s * 0.18, s * 0.16, s * 0.12), 0, 180 * 16)
        # Lid bar
        p.drawLine(QPointF(s * 0.24, s * 0.28), QPointF(s * 0.76, s * 0.28))

        # Can body (tapered)
        body = QPolygonF([
            QPointF(s * 0.30, s * 0.34),
            QPointF(s * 0.34, s * 0.80),
            QPointF(s * 0.66, s * 0.80),
            QPointF(s * 0.70, s * 0.34),
        ])
        p.drawPolygon(body)

        # Slats
        p.drawLine(QPointF(s * 0.44, s * 0.42), QPointF(s * 0.44, s * 0.72))
        p.drawLine(QPointF(s * 0.56, s * 0.42), QPointF(s * 0.56, s * 0.72))

    @classmethod
    def _draw_stop(cls, p: QPainter, s: int, c: QColor):
        """Cross / Cancel badge."""
        p.setBrush(Qt.NoBrush)
        m = s * 0.28
        p.drawLine(QPointF(m, m), QPointF(s - m, s - m))
        p.drawLine(QPointF(s - m, m), QPointF(m, s - m))

    @classmethod
    def _draw_save(cls, p: QPainter, s: int, c: QColor):
        """Clean checkmark save badge."""
        p.setBrush(Qt.NoBrush)
        # Disk outline
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60), s * 0.08, s * 0.08)
        # Checkmark
        check = QPainterPath()
        check.moveTo(s * 0.32, s * 0.52)
        check.lineTo(s * 0.46, s * 0.64)
        check.lineTo(s * 0.68, s * 0.38)
        p.drawPath(check)

    @classmethod
    def _draw_defaults(cls, p: QPainter, s: int, c: QColor):
        """Reset counter-clockwise loop."""
        radius = s * 0.28
        center = QPointF(s * 0.5, s * 0.5)
        rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

        p.setBrush(Qt.NoBrush)
        p.drawArc(rect, int(60 * 16), int(260 * 16))

        # Arrowhead pointing down/left
        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        arrow = QPolygonF([
            QPointF(s * 0.46, s * 0.16),
            QPointF(s * 0.32, s * 0.26),
            QPointF(s * 0.46, s * 0.36),
        ])
        p.drawPolygon(arrow)
        p.setPen(old_pen)

    @classmethod
    def _draw_browse(cls, p: QPainter, s: int, c: QColor):
        """Folder tab outline."""
        path = QPainterPath()
        path.moveTo(s * 0.20, s * 0.26)
        path.lineTo(s * 0.44, s * 0.26)
        path.lineTo(s * 0.52, s * 0.36)
        path.lineTo(s * 0.80, s * 0.36)
        path.lineTo(s * 0.80, s * 0.74)
        path.lineTo(s * 0.20, s * 0.74)
        path.closeSubpath()
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    @classmethod
    def _draw_settings(cls, p: QPainter, s: int, c: QColor):
        """Precision gear / cogwheel with clean hub and notched teeth."""
        p.setBrush(Qt.NoBrush)
        center = QPointF(s * 0.5, s * 0.5)
        # Gear body ring
        p.drawEllipse(center, s * 0.24, s * 0.24)

        # Center core hole
        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawEllipse(center, s * 0.08, s * 0.08)
        p.setPen(old_pen)
        p.setBrush(Qt.NoBrush)

        # 6 radial teeth
        for i in range(6):
            p.save()
            p.translate(center)
            p.rotate(i * 60)
            p.drawLine(QPointF(0, -s * 0.24), QPointF(0, -s * 0.35))
            p.restore()

    @classmethod
    def _draw_shield_path(cls, s: int) -> QPainterPath:
        """Returns the reusable shield outline path."""
        shield = QPainterPath()
        shield.moveTo(s * 0.5, s * 0.15)
        shield.lineTo(s * 0.80, s * 0.26)
        shield.lineTo(s * 0.80, s * 0.54)
        shield.cubicTo(s * 0.80, s * 0.74, s * 0.5, s * 0.86, s * 0.5, s * 0.86)
        shield.cubicTo(s * 0.5, s * 0.86, s * 0.20, s * 0.74, s * 0.20, s * 0.54)
        shield.lineTo(s * 0.20, s * 0.26)
        shield.closeSubpath()
        return shield

    @classmethod
    def _draw_shield(cls, p: QPainter, s: int, c: QColor):
        """Default security shield with checkmark."""
        cls._draw_shield_ok(p, s, c)

    @classmethod
    def _draw_shield_ok(cls, p: QPainter, s: int, c: QColor):
        """Security shield with checkmark (Protected state)."""
        shield = cls._draw_shield_path(s)
        # Subtle translucent background tint
        bg = QColor(c)
        bg.setAlpha(35)
        p.fillPath(shield, QBrush(bg))

        p.setBrush(Qt.NoBrush)
        p.drawPath(shield)

        # Inner bold checkmark
        check = QPainterPath()
        check.moveTo(s * 0.35, s * 0.50)
        check.lineTo(s * 0.46, s * 0.62)
        check.lineTo(s * 0.66, s * 0.38)
        p.drawPath(check)

    @classmethod
    def _draw_shield_warn(cls, p: QPainter, s: int, c: QColor):
        """Security shield with exclamation mark (Warning state)."""
        shield = cls._draw_shield_path(s)
        bg = QColor(c)
        bg.setAlpha(35)
        p.fillPath(shield, QBrush(bg))

        p.setBrush(Qt.NoBrush)
        p.drawPath(shield)

        # Exclamation mark bar & dot
        p.drawLine(QPointF(s * 0.5, s * 0.34), QPointF(s * 0.5, s * 0.55))
        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(s * 0.5, s * 0.68), s * 0.04, s * 0.04)
        p.setPen(old_pen)

    @classmethod
    def _draw_shield_error(cls, p: QPainter, s: int, c: QColor):
        """Security shield with cross mark (Critical/Unprotected state)."""
        shield = cls._draw_shield_path(s)
        bg = QColor(c)
        bg.setAlpha(35)
        p.fillPath(shield, QBrush(bg))

        p.setBrush(Qt.NoBrush)
        p.drawPath(shield)

        # Cross mark (X)
        p.drawLine(QPointF(s * 0.38, s * 0.40), QPointF(s * 0.62, s * 0.64))
        p.drawLine(QPointF(s * 0.62, s * 0.40), QPointF(s * 0.38, s * 0.64))

    @classmethod
    def _draw_info(cls, p: QPainter, s: int, c: QColor):
        """Clean circular info badge with centered 'i'."""
        p.setBrush(Qt.NoBrush)
        center = QPointF(s * 0.5, s * 0.5)
        radius = s * 0.34
        p.drawEllipse(center, radius, radius)

        # Dot of the 'i'
        old_pen = p.pen()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(s * 0.5, s * 0.34), s * 0.04, s * 0.04)
        p.setPen(old_pen)

        # Stem of the 'i'
        p.drawLine(QPointF(s * 0.5, s * 0.44), QPointF(s * 0.5, s * 0.68))

    @classmethod
    def _draw_about(cls, p: QPainter, s: int, c: QColor):
        """Alias for info icon."""
        cls._draw_info(p, s, c)
