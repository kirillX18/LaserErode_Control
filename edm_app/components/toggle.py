"""
toggle.py — тумблер (двухпозиционный переключатель-«ползунок»).

Switch в духе остального интерфейса: серый овал с белым кружком слева — выкл,
зелёный овал с кружком справа — вкл (те же цвета, что у индикаторов состояния).
Наследует QCheckBox, поэтому ведёт себя как обычный флажок — сигнал
toggled(bool), setChecked(), фокус с клавиатуры и переключение пробелом, — но
рисуется сам, а стандартный индикатор скрыт. Ход кружка плавно анимируется.
"""

from PyQt5.QtCore import (
    Qt, QSize, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen
from PyQt5.QtWidgets import QCheckBox

from .. import theme


class ToggleSwitch(QCheckBox):
    """Переключатель-«ползунок» (switch) с плавным ходом кружка."""

    _W = 46          # ширина дорожки
    _H = 24          # высота дорожки
    _MARGIN = 3      # зазор кружка от края дорожки

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pos = 0.0   # 0 — выкл (кружок слева), 1 — вкл (справа)
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    # ---- анимируемое свойство положения кружка ----
    def getKnobPos(self) -> float:
        return self._pos

    def setKnobPos(self, value: float) -> None:
        self._pos = value
        self.update()

    knobPos = pyqtProperty(float, fget=getKnobPos, fset=setKnobPos)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    # ---- поведение QCheckBox ----
    def setChecked(self, on: bool) -> None:
        super().setChecked(on)
        # начальная установка (до показа): встать на место без анимации
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._W, self._H)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._W, self._H)

    def hitButton(self, pos) -> bool:
        # переключать по клику в любой точке виджета, а не только по индикатору
        return self.rect().contains(pos)

    # ---- отрисовка ----
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        top = (self.height() - self._H) / 2.0
        track = QRectF(0.0, top, float(self._W), float(self._H))

        # цвет дорожки интерполируется серый → зелёный по ходу кружка
        off = QColor(theme.Palette.OFF)
        on = QColor(theme.Palette.GREEN)
        t = self._pos
        track_col = QColor(
            round(off.red()   + (on.red()   - off.red())   * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue()  + (on.blue()  - off.blue())  * t),
        )
        if not self.isEnabled():
            track_col = QColor(theme.Palette.GRAY)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(track_col))
        r = track.height() / 2.0
        p.drawRoundedRect(track, r, r)

        # кружок
        d = self._H - 2 * self._MARGIN
        x = track.left() + self._MARGIN + (self._W - 2 * self._MARGIN - d) * t
        y = track.top() + self._MARGIN
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.Palette.FOCUS), 2))
        else:
            p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QRectF(x, y, float(d), float(d)))
        p.end()
