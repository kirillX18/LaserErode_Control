from PyQt5.QtCore import QEvent, QPointF, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QPushButton, QGraphicsDropShadowEffect

from .. import theme


class _RoleButton(QPushButton):
    """Базовая кнопка с семантической ролью (определяет стиль через QSS)."""
    role: str = theme.ROLE_PRIMARY
    max_width: int | None = None

    # Параметры анимации «подъёма» (радиус размытия тени, смещение по Y, мс).
    _REST = (0.0, 0.0)       # покой: тени нет
    _HOVER = (16.0, 4.0)     # наведение: кнопка приподнята
    _PRESS = (4.0, 1.0)      # нажатие: кнопка «просела»
    _DURATION_HOVER = 130
    _DURATION_PRESS = 90

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        if self.role:
            self.setObjectName(self.role)
        if self.max_width is not None:
            self.setMaximumWidth(self.max_width)

        # Мягкая тень под кнопкой — её параметры и анимируются.
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setColor(QColor(0, 0, 0, 90))
        self._shadow.setBlurRadius(self._REST[0])
        self._shadow.setOffset(0.0, self._REST[1])
        self.setGraphicsEffect(self._shadow)

        self._blur_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._blur_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._offset_anim = QPropertyAnimation(self._shadow, b"offset", self)
        self._offset_anim.setEasingCurve(QEasingCurve.OutCubic)


    # Анимация
    def _elevate(self, target: tuple[float, float], duration: int) -> None:
        """Плавно перевести тень к (blur, offset_y)."""
        blur, dy = target
        for anim, prop, end in (
            (self._blur_anim, "blur", float(blur)),
            (self._offset_anim, "offset", QPointF(0.0, float(dy))),
        ):
            anim.stop()
            anim.setDuration(duration)
            anim.setEndValue(end)
            anim.start()

    # События мыши и состояния
    def enterEvent(self, event):
        if self.isEnabled():
            self._elevate(self._HOVER, self._DURATION_HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._elevate(self._REST, self._DURATION_HOVER)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.isEnabled():
            self._elevate(self._PRESS, self._DURATION_PRESS)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if not self.isEnabled():
            return
        # после отпускания: если курсор ещё над кнопкой — вернуть «подъём»,
        # иначе вернуть в покой.
        inside = self.rect().contains(event.pos())
        self._elevate(self._HOVER if inside else self._REST,
                      self._DURATION_PRESS)

    def changeEvent(self, event):
        super().changeEvent(event)
        # При отключении кнопки мгновенно убираем тень (нет «зависшего» подъёма).
        if event.type() == QEvent.EnabledChange and not self.isEnabled():
            self._blur_anim.stop()
            self._offset_anim.stop()
            self._shadow.setBlurRadius(self._REST[0])
            self._shadow.setOffset(0.0, self._REST[1])


class PrimaryButton(_RoleButton):
    """Зелёная кнопка по умолчанию (основное действие)."""
    role = theme.ROLE_PRIMARY


class DangerButton(_RoleButton):
    """Широкая красная кнопка (например, «Вернуться в нулевое положение»)."""
    role = theme.ROLE_DANGER


class SmallButton(_RoleButton):
    """Компактная зелёная кнопка шага (+1 / +10)."""
    role = theme.ROLE_SMALL
    max_width = 60


class RedButton(_RoleButton):
    """Компактная красная кнопка (например, «−» в блоках суставов)."""
    role = theme.ROLE_RED
    max_width = 60


class GrayButton(_RoleButton):
    """Серая нейтральная кнопка («Назад»)."""
    role = theme.ROLE_GRAY
    max_width = 90
