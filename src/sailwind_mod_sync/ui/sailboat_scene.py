from __future__ import annotations

import math
import time
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

FRAME_MS = 33


class SailboatScene(QWidget):
    """A looping sailboat-on-the-ocean doodle for the launch splash."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setAutoFillBackground(False)
        self._clock = clock or time.monotonic
        self._last = self._clock()
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(FRAME_MS)

    @property
    def phase(self) -> float:
        return self._phase

    def running(self) -> bool:
        return self._timer.isActive()

    def stop(self) -> None:
        self._timer.stop()

    def _advance(self) -> None:
        now = self._clock()
        dt = max(0.0, min(0.08, now - self._last))
        self._last = now
        self._phase += dt
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        painter.setClipPath(clip)
        self._paint_sky(painter, rect)
        self._paint_sun(painter, rect)
        self._paint_clouds(painter, rect)
        self._paint_birds(painter, rect)
        water_top = rect.height() * 0.52
        self._paint_far_water(painter, rect, water_top)
        self._paint_boat(painter, rect, water_top)
        self._paint_near_water(painter, rect, water_top)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(20, 50, 70, 50), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        painter.end()

    def _paint_sky(self, painter: QPainter, rect) -> None:
        sky = QLinearGradient(0, 0, 0, rect.height() * 0.6)
        sky.setColorAt(0.0, QColor("#8EC8EA"))
        sky.setColorAt(0.55, QColor("#CDE9F7"))
        sky.setColorAt(1.0, QColor("#F8E4C4"))
        painter.fillRect(rect, sky)

    def _paint_sun(self, painter: QPainter, rect) -> None:
        cx = rect.width() * 0.82
        cy = rect.height() * 0.22
        radius = min(rect.width(), rect.height()) * 0.09
        glow = QRadialGradient(cx, cy, radius * 2.4)
        glow.setColorAt(0.0, QColor(255, 224, 130, 90))
        glow.setColorAt(1.0, QColor(255, 224, 130, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), radius * 2.4, radius * 2.4)
        painter.setBrush(QColor("#FFE08A"))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _paint_clouds(self, painter: QPainter, rect) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 210))
        w = rect.width()
        h = rect.height()
        t = self._phase
        self._cloud(painter, (0.12 + 0.02 * math.sin(t * 0.15)) * w, 0.16 * h, 0.16 * w)
        self._cloud(painter, (0.55 + 0.03 * math.sin(t * 0.11 + 1.2)) * w, 0.12 * h, 0.2 * w)

    def _cloud(self, painter: QPainter, x: float, y: float, size: float) -> None:
        painter.drawEllipse(QPointF(x, y), size * 0.34, size * 0.22)
        painter.drawEllipse(QPointF(x + size * 0.28, y + size * 0.04), size * 0.28, size * 0.18)
        painter.drawEllipse(QPointF(x - size * 0.26, y + size * 0.06), size * 0.24, size * 0.16)

    def _paint_birds(self, painter: QPainter, rect) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#4A6578"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        t = self._phase
        self._bird(painter, rect.width() * 0.28, rect.height() * (0.22 + 0.015 * math.sin(t * 1.4)), 10)
        self._bird(painter, rect.width() * 0.36, rect.height() * (0.18 + 0.012 * math.sin(t * 1.1 + 0.8)), 8)

    def _bird(self, painter: QPainter, x: float, y: float, span: float) -> None:
        path = QPainterPath()
        path.moveTo(x - span, y)
        path.quadTo(x - span * 0.35, y - span * 0.45, x, y)
        path.quadTo(x + span * 0.35, y - span * 0.45, x + span, y)
        painter.drawPath(path)

    def _paint_far_water(self, painter: QPainter, rect, water_top: float) -> None:
        width = float(rect.width())
        height = float(rect.height())
        t = self._phase
        layers = (
            (QColor("#2A7EA8"), water_top - 8, 9.0, 54.0, t * 0.7),
            (QColor("#3B9BC4"), water_top + 6, 12.0, 38.0, t * 1.15 + 0.8),
        )
        for color, baseline, amp, length, phase in layers:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(self._wave_path(width, height, baseline, amp, length, phase))

    def _paint_near_water(self, painter: QPainter, rect, water_top: float) -> None:
        width = float(rect.width())
        height = float(rect.height())
        t = self._phase
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#57B3D2"))
        painter.drawPath(self._wave_path(width, height, water_top + 22, 16.0, 28.0, t * 1.7 + 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.4))
        painter.drawPath(self._wave_crest(width, water_top + 22, 16.0, 28.0, t * 1.7 + 1.6))

    def _wave_path(
        self,
        width: float,
        height: float,
        baseline: float,
        amp: float,
        length: float,
        phase: float,
    ) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(0, height)
        step = 6.0
        x = 0.0
        while x <= width + step:
            path.lineTo(x, baseline + math.sin(x / length + phase) * amp)
            x += step
        path.lineTo(width, height)
        path.closeSubpath()
        return path

    def _wave_crest(
        self,
        width: float,
        baseline: float,
        amp: float,
        length: float,
        phase: float,
    ) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(0, baseline + math.sin(phase) * amp)
        step = 6.0
        x = step
        while x <= width + step:
            path.lineTo(x, baseline + math.sin(x / length + phase) * amp)
            x += step
        return path

    def _water_y(self, x: float, water_top: float, phase: float) -> float:
        return water_top + 22 + math.sin(x / 28.0 + phase * 1.7 + 1.6) * 16.0

    def _paint_boat(self, painter: QPainter, rect, water_top: float) -> None:
        width = float(rect.width())
        t = self._phase
        cx = width * (0.40 + 0.03 * math.sin(t * 0.45))
        cy = self._water_y(cx, water_top, t) + 4
        sample = 8.0
        roll = math.atan2(
            self._water_y(cx + sample, water_top, t) - self._water_y(cx - sample, water_top, t),
            sample * 2,
        ) * 0.7
        scale = max(0.7, min(rect.width(), rect.height()) / 240.0)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(math.degrees(roll))
        painter.scale(scale, scale)
        self._draw_boat(painter)
        painter.restore()

    def _draw_boat(self, painter: QPainter) -> None:
        hull = QPainterPath()
        hull.moveTo(-40, 0)
        hull.quadTo(-44, 10, -24, 18)
        hull.lineTo(28, 18)
        hull.quadTo(46, 8, 40, 0)
        hull.closeSubpath()
        painter.setPen(QPen(QColor("#3D2414"), 1.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QColor("#8A5330"))
        painter.drawPath(hull)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#C48A4A"))
        painter.drawRoundedRect(QRectF(-32, -3, 64, 5), 2, 2)
        painter.setBrush(QColor("#6B3B22"))
        painter.drawRoundedRect(QRectF(-8, -10, 16, 10), 2, 2)
        painter.setBrush(QColor("#9FD7F0"))
        painter.drawEllipse(QPointF(0, -5), 3.2, 3.2)
        painter.setPen(QPen(QColor("#3D2414"), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(-6, 0), QPointF(-6, -56))
        mainsail = QPainterPath()
        mainsail.moveTo(-4, -54)
        mainsail.lineTo(30, -8)
        mainsail.lineTo(-4, -8)
        mainsail.closeSubpath()
        painter.setPen(QPen(QColor("#D9C7A0"), 1.0))
        painter.setBrush(QColor("#FFF6E4"))
        painter.drawPath(mainsail)
        jib = QPainterPath()
        jib.moveTo(-8, -46)
        jib.lineTo(-8, -10)
        jib.lineTo(-34, -10)
        jib.closeSubpath()
        painter.setBrush(QColor("#FFEFD2"))
        painter.drawPath(jib)
        flag = QPainterPath()
        flag.moveTo(-6, -56)
        flag.lineTo(12, -51)
        flag.lineTo(-6, -46)
        flag.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#E2573E"))
        painter.drawPath(flag)
