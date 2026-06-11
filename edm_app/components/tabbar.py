from PyQt5.QtCore import QRectF, QTimer
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QTabBar

from .. import theme


class AnimatedTabBar(QTabBar):
    """QTabBar с плавной подсветкой вкладки при наведении курсора."""

    _ACCENT = theme.Palette.ACCENT   # цвет акцента (синий, как у значений)
    _STEP = 0.18                     # доля сближения с целью за тик (плавность)
    _INTERVAL = 16                   # мс между тиками (~60 кадров/с)
    _BAR_HEIGHT = 3                  # толщина акцентной полоски, px
    _SIDE_PAD = 12                   # отступ полоски от краёв вкладки, px

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)          # ловим перемещение без нажатия
        self._hover = -1                     # вкладка под курсором (-1 — нет)
        self._progress: dict[int, float] = {}  # индекс вкладки -> прогресс 0..1
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL)
        self._timer.timeout.connect(self._tick)

    # --- отслеживание наведения ------------------------------------------
    def mouseMoveEvent(self, event):
        idx = self.tabAt(event.pos())
        if idx != self._hover:
            self._hover = idx
            self._ensure_running()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover != -1:
            self._hover = -1
            self._ensure_running()
        super().leaveEvent(event)

    # --- анимация --------------------------------------------------------
    def _ensure_running(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self) -> None:
        """Подтянуть прогресс каждой вкладки к её цели; остановиться, когда всё устоялось."""
        animating = False
        for i in range(self.count()):
            target = 1.0 if i == self._hover else 0.0
            cur = self._progress.get(i, 0.0)
            if abs(cur - target) < 0.01:
                cur = target
            else:
                cur += (target - cur) * self._STEP
                animating = True
            if cur <= 0.0:
                self._progress.pop(i, None)
            else:
                self._progress[i] = cur
        self.update()
        if not animating:
            self._timer.stop()

    # --- отрисовка -------------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)            # сами вкладки (стиль из QSS)
        if not self._progress:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        accent = QColor(self._ACCENT)
        for i, p in self._progress.items():
            if p <= 0.0:
                continue
            rect = self.tabRect(i)

            # лёгкий фоновый налёт акцентного цвета
            bg = QColor(accent)
            bg.setAlpha(int(26 * p))
            painter.fillRect(rect, bg)

            # «вырастающая» из центра нижняя полоска
            full = max(0, rect.width() - 2 * self._SIDE_PAD)
            w = full * p
            x = rect.center().x() - w / 2.0
            y = rect.bottom() - self._BAR_HEIGHT
            bar = QColor(accent)
            bar.setAlpha(int(235 * p))
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, w, self._BAR_HEIGHT), 1.5, 1.5)
            painter.fillPath(path, bar)
        painter.end()
