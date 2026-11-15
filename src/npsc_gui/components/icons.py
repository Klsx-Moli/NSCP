"""Vector icons painted in code.

No icon font and no bitmap assets: every glyph is drawn with ``QPainter`` at the
requested size and colour, so it stays sharp at any Windows DPI scale and never
falls back to a missing-glyph box.

Usage::

    label.setPixmap(icon_pixmap("check", 16, "#3CC98C"))
    button.setIcon(QIcon(icon_pixmap("copy", 16)))
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from npsc_gui.design.style import active_theme

# Stroke width relative to the icon square, tuned for a 16 px icon.
_STROKE_RATIO = 0.085


def _pen(colour: str, size: int, width_ratio: float = _STROKE_RATIO) -> QPen:
    pen = QPen(QColor(colour))
    pen.setWidthF(max(1.1, size * width_ratio))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_search(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size))
    radius = rect.width() * 0.29
    centre = QPointF(rect.left() + rect.width() * 0.42, rect.top() + rect.height() * 0.42)
    painter.drawEllipse(centre, radius, radius)
    painter.drawLine(
        QPointF(centre.x() + radius * 0.72, centre.y() + radius * 0.72),
        QPointF(rect.right() - rect.width() * 0.14, rect.bottom() - rect.height() * 0.14),
    )


def _draw_check(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size, 0.11))
    path = QPainterPath()
    path.moveTo(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.53)
    path.lineTo(rect.left() + rect.width() * 0.41, rect.top() + rect.height() * 0.76)
    path.lineTo(rect.right() - rect.width() * 0.16, rect.top() + rect.height() * 0.25)
    painter.drawPath(path)


def _draw_copy(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size))
    offset = rect.width() * 0.2
    back = QRectF(
        rect.left() + offset,
        rect.top() + offset,
        rect.width() - offset * 1.4,
        rect.height() - offset * 1.4,
    )
    front = QRectF(
        rect.left() + rect.width() * 0.1,
        rect.top() + rect.height() * 0.1,
        rect.width() - offset * 1.4,
        rect.height() - offset * 1.4,
    )
    painter.drawRoundedRect(back, 2.0, 2.0)
    painter.setBrush(QColor(active_theme().palette.bg_surface))
    painter.drawRoundedRect(front, 2.0, 2.0)


def _draw_settings(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size))
    centre = rect.center()
    outer = rect.width() * 0.33
    inner = rect.width() * 0.14
    painter.drawEllipse(centre, outer, outer)
    painter.drawEllipse(centre, inner, inner)
    import math

    for index in range(6):
        angle = math.radians(index * 60)
        start = QPointF(
            centre.x() + math.cos(angle) * outer * 1.02,
            centre.y() + math.sin(angle) * outer * 1.02,
        )
        end = QPointF(
            centre.x() + math.cos(angle) * outer * 1.45,
            centre.y() + math.sin(angle) * outer * 1.45,
        )
        painter.drawLine(start, end)


def _draw_help(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size))
    painter.drawEllipse(rect.adjusted(1.5, 1.5, -1.5, -1.5))
    font = painter.font()
    font.setPixelSize(int(size * 0.62))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "?")


def _draw_info(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size))
    painter.drawEllipse(rect.adjusted(1.5, 1.5, -1.5, -1.5))
    font = painter.font()
    font.setPixelSize(int(size * 0.62))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "i")


def _draw_chevron(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size, 0.1))
    path = QPainterPath()
    path.moveTo(rect.left() + rect.width() * 0.25, rect.top() + rect.height() * 0.4)
    path.lineTo(rect.left() + rect.width() * 0.5, rect.top() + rect.height() * 0.62)
    path.lineTo(rect.right() - rect.width() * 0.25, rect.top() + rect.height() * 0.4)
    painter.drawPath(path)


def _draw_chevron_left(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size, 0.1))
    path = QPainterPath()
    path.moveTo(rect.left() + rect.width() * 0.6, rect.top() + rect.height() * 0.22)
    path.lineTo(rect.left() + rect.width() * 0.36, rect.center().y())
    path.lineTo(rect.left() + rect.width() * 0.6, rect.bottom() - rect.height() * 0.22)
    painter.drawPath(path)


def _draw_chevron_right(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size, 0.1))
    path = QPainterPath()
    path.moveTo(rect.right() - rect.width() * 0.6, rect.top() + rect.height() * 0.22)
    path.lineTo(rect.right() - rect.width() * 0.36, rect.center().y())
    path.lineTo(rect.right() - rect.width() * 0.6, rect.bottom() - rect.height() * 0.22)
    painter.drawPath(path)


def _draw_folder(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size))
    path = QPainterPath()
    path.moveTo(rect.left() + rect.width() * 0.1, rect.top() + rect.height() * 0.72)
    path.lineTo(rect.left() + rect.width() * 0.1, rect.top() + rect.height() * 0.3)
    path.lineTo(rect.left() + rect.width() * 0.42, rect.top() + rect.height() * 0.3)
    path.lineTo(rect.left() + rect.width() * 0.52, rect.top() + rect.height() * 0.42)
    path.lineTo(rect.right() - rect.width() * 0.1, rect.top() + rect.height() * 0.42)
    path.lineTo(rect.right() - rect.width() * 0.1, rect.top() + rect.height() * 0.72)
    path.closeSubpath()
    painter.drawPath(path)


def _draw_save(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size))
    body = rect.adjusted(rect.width() * 0.14, rect.height() * 0.14,
                        -rect.width() * 0.14, -rect.height() * 0.14)
    painter.drawRoundedRect(body, 2.0, 2.0)
    painter.drawRect(
        QRectF(
            body.left() + body.width() * 0.28,
            body.top(),
            body.width() * 0.44,
            body.height() * 0.34,
        )
    )


def _draw_close(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size, 0.1))
    inset = rect.width() * 0.3
    painter.drawLine(
        QPointF(rect.left() + inset, rect.top() + inset),
        QPointF(rect.right() - inset, rect.bottom() - inset),
    )
    painter.drawLine(
        QPointF(rect.right() - inset, rect.top() + inset),
        QPointF(rect.left() + inset, rect.bottom() - inset),
    )


def _draw_spark(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size, 0.09))
    centre = rect.center()
    painter.drawLine(
        QPointF(centre.x(), rect.top() + rect.height() * 0.12),
        QPointF(centre.x(), rect.bottom() - rect.height() * 0.12),
    )
    painter.drawLine(
        QPointF(rect.left() + rect.width() * 0.12, centre.y()),
        QPointF(rect.right() - rect.width() * 0.12, centre.y()),
    )
    diagonal = rect.width() * 0.24
    painter.drawLine(
        QPointF(centre.x() - diagonal, centre.y() - diagonal),
        QPointF(centre.x() + diagonal, centre.y() + diagonal),
    )
    painter.drawLine(
        QPointF(centre.x() + diagonal, centre.y() - diagonal),
        QPointF(centre.x() - diagonal, centre.y() + diagonal),
    )


def _draw_layers(painter: QPainter, rect: QRectF, colour: str, size: int) -> None:
    painter.setPen(_pen(colour, size, 0.085))
    for index, ratio in enumerate((0.68, 0.5, 0.32)):
        y = rect.top() + rect.height() * ratio
        path = QPainterPath()
        path.moveTo(rect.left() + rect.width() * 0.12, y)
        path.lineTo(rect.center().x(), y - rect.height() * 0.16)
        path.lineTo(rect.right() - rect.width() * 0.12, y)
        painter.drawPath(path)


_DRAWERS = {
    "search": _draw_search,
    "check": _draw_check,
    "copy": _draw_copy,
    "settings": _draw_settings,
    "help": _draw_help,
    "info": _draw_info,
    "chevron-down": _draw_chevron,
    "chevron-left": _draw_chevron_left,
    "chevron-right": _draw_chevron_right,
    "folder": _draw_folder,
    "save": _draw_save,
    "close": _draw_close,
    "spark": _draw_spark,
    "layers": _draw_layers,
}


def icon_pixmap(
    name: str,
    size: int = 16,
    colour: str | None = None,
    *,
    device_pixel_ratio: float = 1.0,
) -> QPixmap:
    """Paint ``name`` into a transparent pixmap of ``size`` logical pixels."""
    theme = active_theme()
    colour = colour or theme.palette.text_secondary
    ratio = max(1.0, device_pixel_ratio)
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = QRectF(0.6, 0.6, size - 1.2, size - 1.2)
    drawer = _DRAWERS.get(name)
    if drawer is not None:
        drawer(painter, rect, colour, size)
    painter.end()
    return pixmap


def icon(name: str, size: int = 16, colour: str | None = None) -> QIcon:
    """Return a themed ``QIcon`` for ``name``."""
    return QIcon(icon_pixmap(name, size, colour))


def icon_names() -> tuple[str, ...]:
    return tuple(sorted(_DRAWERS))


__all__ = ["icon", "icon_pixmap", "icon_names"]
