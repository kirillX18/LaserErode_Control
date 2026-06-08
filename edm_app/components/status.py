from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QWidget, QHBoxLayout, QProgressBar

from .. import theme


class StatusDot(QLabel):
    """Маленький цветной кружок-индикатор."""

    def __init__(self, state: str = "off", size: int = 12, parent=None):
        super().__init__(parent)
        self._size = size
        self.set_state(state)

    def set_state(self, state: str) -> None:
        self.setStyleSheet(theme.dot_style(state, self._size))


class StatusBadge(QLabel):
    """Текстовая «пилюля» состояния (цвет + подпись)."""

    def __init__(self, text: str = "—", state: str = "off", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_state(text, state)

    def set_state(self, text: str, state: str = "off") -> None:
        self.setText(text)
        self.setStyleSheet(theme.badge_style(state))


class MetricRow(QWidget):
    """Строка «подпись … значение» с возможностью подкрасить значение."""

    def __init__(self, label: str, value: str = "—", parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 1, 0, 1)
        self._key = QLabel(label)
        self._val = QLabel(value)
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self._key)
        h.addStretch()
        h.addWidget(self._val)

    def set_value(self, value, state: str | None = None) -> None:
        self._val.setText(str(value))
        if state is None:
            self._val.setStyleSheet(theme.value_style())
        else:
            fg, _ = theme.state_colors(state)
            self._val.setStyleSheet(f"color:{fg}; font-weight:bold;")


class MeterBar(QProgressBar):
    """Горизонтальная шкала 0…100 % с цветом по состоянию."""

    def __init__(self, kind: str = "ok", parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.setStyleSheet(theme.meter_style(kind))

    def set_fraction(self, fraction: float) -> None:
        self.setValue(max(0, min(100, int(round(fraction * 100)))))


class IndicatorRow(QWidget):
    """Строка-индикатор: [точка] подпись … [состояние].

    Используется в списках условий запуска и сводках состояния, где важно
    цветом показать «ок / не ок» (HTML — строки со светофором-точкой).
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 1, 0, 1)
        self.dot = StatusDot("off", 10)
        self._key = QLabel(label)
        self._val = QLabel("—")
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self.dot)
        h.addWidget(self._key)
        h.addStretch()
        h.addWidget(self._val)

    def set_state(self, state: str, text: str) -> None:
        self.dot.set_state(state)
        self._val.setText(text)
        fg, _ = theme.state_colors(state)
        self._val.setStyleSheet(f"color:{fg}; font-weight:bold;")


class LastMessageBar(QLabel):
    """Компактная строка последнего сообщения/результата операции.

    Подключается к сигналу DeviceController.logMessage и показывает последнее
    событие прямо на вкладке — чтобы реакция на действие (в т. ч. ошибка) была
    видна локально, а не только в общем журнале на другой странице.
    """

    def __init__(self, parent=None):
        super().__init__("Готов к работе", parent)
        self.setWordWrap(True)
        self._apply("info")

    def _apply(self, level: str) -> None:
        color = {"warning": theme.Palette.WARN,
                 "error": theme.Palette.ERR}.get(level, theme.Palette.OFF)
        self.setStyleSheet(f"color:{color}; padding:3px 2px;")

    def set_message(self, level: str, text: str) -> None:
        self._apply(level)
        self.setText(text)
