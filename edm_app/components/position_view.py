"""
position_view.py — 3D-визуализация положения лазерной головки над столом.

Сцена проста (стол-сетка + головка + луч + оси), поэтому рисуется средствами
QPainter — без OpenGL и без зависимостей. Камера-орбита: ЛКМ — поворот,
колесо — зум, двойной клик — сброс.

Положение задаётся долями [0..1] по каждой оси через set_position():
    X, Y — положение инструмента манипулятора над зоной обработки;
    Z     — высота инструмента над зоной.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont
from PyQt5.QtWidgets import QWidget, QSizePolicy

from ..theme import Palette

_S = 100.0   # сторона стола в условных единицах сцены
_H = 64.0    # высота рабочей зоны по Z


class PositionView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(340, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAutoFillBackground(True)

        self._x = 0.0          # доли [0..1]
        self._y = 0.0
        self._z = 0.0
        self._moving = False

        # подписи значений (реальные, для текста у маркера)
        self._labels = ("X 0", "Y 0", "Z 0")

        self._center = (_S / 2, _S / 2, _H / 2)
        self._extent = max(_S, _H)

        self._yaw = math.radians(35)
        self._pitch = math.radians(58)
        self._zoom = 1.0
        self._last = None
        self._tf = None

    # ---- данные --------------------------------------------------------
    def set_position(self, xf, yf, zf, moving=False, labels=None) -> None:
        self._x = max(0.0, min(1.0, xf))
        self._y = max(0.0, min(1.0, yf))
        self._z = max(0.0, min(1.0, zf))
        self._moving = moving
        if labels:
            self._labels = labels
        self.update()

    def _reset_view(self) -> None:
        self._yaw = math.radians(35)
        self._pitch = math.radians(58)
        self._zoom = 1.0

    # ---- камера --------------------------------------------------------
    def _prepare(self) -> None:
        w, h = self.width(), self.height()
        self._tf = (
            math.cos(self._yaw), math.sin(self._yaw),
            math.cos(self._pitch), math.sin(self._pitch),
            (min(w, h) * 0.60 / self._extent) * self._zoom,
            w / 2, h / 2,
        )

    def _project(self, p):
        cy, sy, cp, sp, scale, ox, oy = self._tf
        x = p[0] - self._center[0]; y = p[1] - self._center[1]; z = p[2] - self._center[2]
        x1 = x * cy - y * sy
        y1 = x * sy + y * cy
        z2 = y1 * sp + z * cp
        return QPointF(ox + x1 * scale, oy - z2 * scale)

    # ---- мышь ----------------------------------------------------------
    def mousePressEvent(self, e):
        self._last = e.pos()

    def mouseMoveEvent(self, e):
        if self._last is None:
            return
        d = e.pos() - self._last
        self._last = e.pos()
        self._yaw += d.x() * 0.01
        self._pitch += d.y() * 0.01
        self._pitch = max(0.05, min(math.pi - 0.05, self._pitch))
        self.update()

    def mouseReleaseEvent(self, e):
        self._last = None

    def wheelEvent(self, e):
        self._zoom *= 1.0015 ** e.angleDelta().y()
        self._zoom = max(0.3, min(6.0, self._zoom))
        self.update()

    def mouseDoubleClickEvent(self, e):
        self._reset_view()
        self.update()

    # ---- отрисовка -----------------------------------------------------
    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing, True)
        qp.fillRect(self.rect(), QColor("#1e2127"))
        self._prepare()

        self._draw_table(qp)
        self._draw_axes(qp)
        self._draw_laser(qp)
        qp.end()

    def _draw_table(self, qp: QPainter) -> None:
        step = _S / 10.0
        qp.setPen(QPen(QColor(80, 90, 105), 1))
        i = 0.0
        while i <= _S + 1e-6:
            qp.drawLine(self._project((i, 0, 0)), self._project((i, _S, 0)))
            qp.drawLine(self._project((0, i, 0)), self._project((_S, i, 0)))
            i += step
        # контур стола
        qp.setPen(QPen(QColor(120, 135, 155), 2))
        qp.drawPolygon(QPolygonF([self._project(c) for c in (
            (0, 0, 0), (_S, 0, 0), (_S, _S, 0), (0, _S, 0))]))

    def _draw_axes(self, qp: QPainter) -> None:
        o = (0, 0, 0)
        origin = self._project(o)
        f = QFont("Sans Serif", 8, QFont.Bold)
        qp.setFont(f)
        for tip, col, name in (((_S * 0.5, 0, 0), QColor("#e25555"), "X"),
                               ((0, _S * 0.5, 0), QColor("#55cc55"), "Y"),
                               ((0, 0, _H * 0.6), QColor("#5599ee"), "Z")):
            p = self._project(tip)
            qp.setPen(QPen(col, 2))
            qp.drawLine(origin, p)
            qp.drawText(p + QPointF(3, 3), name)

    def _draw_laser(self, qp: QPainter) -> None:
        hx, hy, hz = self._x * _S, self._y * _S, self._z * _H
        head = self._project((hx, hy, hz))
        foot = self._project((hx, hy, 0.0))      # проекция на стол (точка реза)

        accent = QColor(Palette.WARN if self._moving else "#d0d8e6")

        # вертикальный «опускной» луч от головки к столу
        beam = QColor(255, 70, 70)
        qp.setPen(QPen(beam, 2, Qt.DashLine))
        qp.drawLine(head, foot)

        # пятно на столе
        qp.setPen(QPen(beam, 1))
        qp.setBrush(QBrush(QColor(255, 70, 70, 90)))
        qp.drawEllipse(foot, 6, 3)

        # головка-маркер (ромб + кружок)
        size = 8
        diamond = QPolygonF([
            head + QPointF(0, -size), head + QPointF(size, 0),
            head + QPointF(0, size), head + QPointF(-size, 0)])
        qp.setPen(QPen(QColor("#202428"), 1))
        qp.setBrush(QBrush(accent))
        qp.drawPolygon(diamond)
        qp.setBrush(QBrush(beam))
        qp.setPen(Qt.NoPen)
        qp.drawEllipse(head, 3, 3)

        # подпись координат у головки
        qp.setPen(QColor("#e6ebf2"))
        qp.setFont(QFont("Sans Serif", 8, QFont.Bold))
        txt = "  ".join(self._labels)
        qp.drawText(head + QPointF(12, -8), txt)
